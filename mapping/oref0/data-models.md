# oref0 Data Models

This document describes the core data structures used by oref0's determine-basal algorithm.

## Input Data Structures

### profile

The profile contains user settings, therapy parameters, and safety limits.

**Source**: `oref0:examples/profile.json`, `oref0:lib/profile/index.js`

```json
{
  "dia": 6,
  "curve": "rapid-acting",
  "useCustomPeakTime": false,
  "insulinPeakTime": 75,
  
  "current_basal": 1.0,
  "basalprofile": [
    { "minutes": 0, "rate": 1.0, "start": "00:00:00", "i": 0 }
  ],
  "max_daily_basal": 1.0,
  
  "sens": 50,
  "isfProfile": {
    "sensitivities": [
      { "offset": 0, "sensitivity": 50, "start": "00:00:00" }
    ],
    "units": "mg/dL"
  },
  
  "carb_ratio": 10,
  "carb_ratios": {
    "schedule": [
      { "offset": 0, "ratio": 10, "start": "00:00:00" }
    ],
    "units": "grams"
  },
  
  "min_bg": 100,
  "max_bg": 100,
  "bg_targets": {
    "targets": [
      { "offset": 0, "min_bg": 100, "max_bg": 100, "start": "00:00:00" }
    ],
    "units": "mg/dL"
  },
  
  "max_iob": 6,
  "max_basal": 4,
  "max_daily_safety_multiplier": 4,
  "current_basal_safety_multiplier": 5,
  
  "autosens_max": 2,
  "autosens_min": 0.5,
  
  "min_5m_carbimpact": 8,
  "maxCOB": 120,
  "remainingCarbsCap": 90,
  
  "enableUAM": true,
  "enableSMB_always": false,
  "enableSMB_with_bolus": true,
  "enableSMB_with_COB": true,
  "enableSMB_with_temptarget": false,
  "enableSMB_after_carbs": true,
  "enableSMB_high_bg": false,
  "enableSMB_high_bg_target": null,
  "maxSMBBasalMinutes": 75,
  "maxUAMSMBBasalMinutes": 30,
  "SMBInterval": 3,
  "bolus_increment": 0.1,
  
  "out_units": "mg/dL",
  "temptargetSet": false
}
```

#### Key Profile Fields

| Field | Type | Description |
|-------|------|-------------|
| `dia` | number | Duration of Insulin Action in hours (minimum 3, recommend 5+ for exponential curves) |
| `curve` | string | Insulin curve type: `bilinear`, `rapid-acting`, or `ultra-rapid` |
| `current_basal` | number | Current scheduled basal rate (U/hr) |
| `sens` | number | Current Insulin Sensitivity Factor (mg/dL per unit) |
| `carb_ratio` | number | Current Carb Ratio (grams per unit) |
| `min_bg` / `max_bg` | number | Target BG range (mg/dL) |
| `max_iob` | number | Maximum IOB allowed (units) |
| `max_basal` | number | Maximum temp basal rate (U/hr) |
| `min_5m_carbimpact` | number | Minimum assumed carb absorption rate (mg/dL per 5 min) |
| `enableUAM` | boolean | Enable Unannounced Meal detection |
| `enableSMB_*` | boolean | Various SMB enable conditions |

### glucose_status

Current CGM reading with recent trends.

**Source**: `oref0:examples/glucose.json`, `oref0:bin/oref0-determine-basal.js`

```json
{
  "glucose": 101,
  "date": 1527924300000,
  "delta": -1,
  "short_avgdelta": -0.5,
  "long_avgdelta": 0.2,
  "noise": 1,
  "device": "fakecgm"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `glucose` | number | Current BG value (mg/dL) |
| `date` | number | Timestamp (milliseconds since epoch) |
| `delta` | number | 5-minute change (mg/dL) |
| `short_avgdelta` | number | ~15-minute average rate of change |
| `long_avgdelta` | number | ~45-minute average rate of change |
| `noise` | number | CGM noise level (1=clean, 2=light, 3+=noisy) |
| `device` | string | CGM device identifier |

### iob_data

Array of IOB projections at 5-minute intervals for prediction calculations.

**Source**: `oref0:examples/iob.json`, `oref0:lib/iob/total.js`

```json
[
  {
    "iob": -0.106,
    "activity": 0.0002,
    "basaliob": -0.486,
    "bolusiob": 0.38,
    "netbasalinsulin": -0.5,
    "bolusinsulin": 0.4,
    "time": "2018-06-02T07:30:00.000Z",
    "lastBolusTime": 1527923100000,
    "lastTemp": {
      "rate": 0,
      "timestamp": "2018-06-02T00:00:00-07:00",
      "started_at": "2018-06-02T07:00:00.000Z",
      "date": 1527922800000,
      "duration": 31
    },
    "iobWithZeroTemp": {
      "iob": -0.106,
      "activity": 0.0002,
      "basaliob": -0.486,
      "bolusiob": 0.38
    }
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `iob` | number | Total Insulin on Board (units) |
| `activity` | number | Current insulin activity (units/min) |
| `basaliob` | number | IOB from temp basals (can be negative) |
| `bolusiob` | number | IOB from boluses |
| `netbasalinsulin` | number | Net basal insulin delivered |
| `bolusinsulin` | number | Total bolus insulin delivered |
| `time` | string | Timestamp for this IOB calculation |
| `lastBolusTime` | number | Time of last bolus (for SMB timing) |
| `lastTemp` | object | Most recent temp basal from pump history |
| `iobWithZeroTemp` | object | IOB projection if temp basals were zero (for ZTpredBG) |

### meal_data

Carb and meal absorption data.

**Source**: `oref0:examples/meal.json`, `oref0:lib/meal/total.js`

```json
{
  "carbs": 20,
  "nsCarbs": 20,
  "bwCarbs": 0,
  "journalCarbs": 0,
  "mealCOB": 0,
  "currentDeviation": -1.21,
  "maxDeviation": 1.74,
  "minDeviation": 0.1,
  "slopeFromMaxDeviation": -0.983,
  "slopeFromMinDeviation": 0,
  "allDeviations": [-1, 0, 2],
  "lastCarbTime": 1527923100000,
  "bwFound": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `carbs` | number | Total carbs entered in meal window (6h) |
| `mealCOB` | number | Current Carbs on Board remaining |
| `currentDeviation` | number | Current BG deviation from expected (mg/dL/5m) |
| `maxDeviation` | number | Peak positive deviation in recent history |
| `minDeviation` | number | Minimum deviation in recent history |
| `slopeFromMaxDeviation` | number | Rate of change from peak deviation |
| `slopeFromMinDeviation` | number | Rate of change from minimum deviation |
| `lastCarbTime` | number | Timestamp of most recent carb entry |
| `bwFound` | boolean | Bolus Wizard activity detected (A52 risk) |

### autosens_data

Sensitivity ratio from autosens algorithm.

**Source**: `oref0:lib/determine-basal/autosens.js`

```json
{
  "ratio": 1.0
}
```

| Field | Type | Description |
|-------|------|-------------|
| `ratio` | number | Sensitivity ratio (1.0 = normal, <1 = more sensitive, >1 = more resistant) |

### currenttemp

Currently running temporary basal.

**Source**: `oref0:examples/temp_basal.json`

```json
{
  "rate": 0,
  "duration": 30,
  "temp": "absolute"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `rate` | number | Current temp basal rate (U/hr) |
| `duration` | number | Remaining duration (minutes) |
| `temp` | string | Temp type (always "absolute") |

## Output Data Structures

### rT (requestedTemp / suggested)

The algorithm output containing recommendations.

**Source**: `oref0:examples/suggested.json`, `oref0:lib/determine-basal/determine-basal.js#L428-L437`

```json
{
  "temp": "absolute",
  "bg": 101,
  "tick": "-1",
  "eventualBG": 106,
  "sensitivityRatio": 1,
  "insulinReq": -0.12,
  "reservoir": null,
  "deliverAt": "2018-06-02T07:25:00.000Z",
  
  "predBGs": {
    "IOB": [101, 100, 98, 97, 97, 96, 95, 95, 94, ...],
    "ZT": [101, 100, 99, 98, 97, 96, 96, 95, 96, ...],
    "COB": [101, 102, 103, 105, 107, ...],
    "UAM": [101, 100, 99, 98, 97, ...]
  },
  
  "COB": 0,
  "IOB": -0.106,
  "BGI": "0",
  "deviation": "0",
  "ISF": "50",
  "CR": 10,
  "target_bg": "100",
  
  "reason": "COB: 0, Dev: 0, BGI: 0, ISF: 50, CR: 10, Target: 100, minPredBG 94...",
  
  "rate": 0,
  "duration": 30,
  "units": 0.3
}
```

| Field | Type | Description |
|-------|------|-------------|
| `bg` | number | Current BG |
| `tick` | string | BG change indicator ("+5" or "-3") |
| `eventualBG` | number | Predicted eventual BG |
| `sensitivityRatio` | number | Applied sensitivity ratio |
| `insulinReq` | number | Calculated insulin requirement (units) |
| `predBGs` | object | Prediction arrays (IOB, ZT, COB, UAM) |
| `COB` | number | Current Carbs on Board |
| `IOB` | number | Current Insulin on Board |
| `BGI` | string | Blood Glucose Impact (mg/dL per 5 min) |
| `reason` | string | Human-readable explanation of decision |
| `rate` | number | Recommended temp basal rate (U/hr) |
| `duration` | number | Recommended temp basal duration (minutes) |
| `units` | number | Recommended SMB size (units), if any |
| `carbsReq` | number | Carbs required to prevent low (optional) |

## Terminology Mapping

| oref0 Term | Alignment Term | Loop Equivalent | AAPS Equivalent |
|------------|---------------|-----------------|-----------------|
| `iob` | Insulin on Board | `insulinOnBoard` | `iob` |
| `activity` | Insulin Activity | `insulinActivityContribution` | `activity` |
| `mealCOB` | Carbs on Board | `carbsOnBoard` | `cob` |
| `sens` | ISF | `insulinSensitivity` | `sens` |
| `carb_ratio` | CR | `carbRatio` | `ic` |
| `eventualBG` | Eventual BG | `predictedGlucose.last` | `eventualBG` |
| `predBGs.IOB` | IOB Prediction | `predictedGlucose` | `predBGsIOB` |
| `deviation` | Deviation | N/A (uses RC) | `deviation` |
| `autosens.ratio` | Sensitivity Ratio | `sensitivityRatio` (via RC) | `autosensRatio` |
