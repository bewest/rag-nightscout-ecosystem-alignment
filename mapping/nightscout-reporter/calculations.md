# Nightscout Reporter: Calculations

This document describes how Nightscout Reporter calculates IOB, COB, TIR, and other statistics from Nightscout data.

---

## Overview

Reporter implements calculations for:

1. **IOB (Insulin on Board)** - Active insulin remaining from boluses
2. **COB (Carbs on Board)** - Unabsorbed carbohydrates
3. **TIR (Time in Range)** - Percentage of readings in target range
4. **Statistical aggregations** - Averages, variance, standard deviation

---

## IOB Calculation

### Method: `calcIOB`

```dart
CalcIOBData calcIOB(ProfileGlucData profile, DateTime time) {
  var dia = 3.0;  // Default DIA: 3 hours
  var sens = 0.0;
  var check = time.hour * 3600 + time.minute * 60 + time.second;

  if (profile != null) {
    dia = profile.store?.dia ?? dia;
    sens = profile.store?.listSens?.lastWhere(
        (e) => e.timeForCalc <= check, orElse: () => null)?.value ?? sens;
  }

  var scaleFactor = 3.0 / dia;
  var peak = 75.0;  // Peak activity at 75 minutes (scaled)
  var ret = CalcIOBData(0.0, 0.0, this);

  if (insulin != null) {
    var bolusTime = createdAt.millisecondsSinceEpoch;
    var minAgo = scaleFactor * (time.millisecondsSinceEpoch - bolusTime) / 1000 / 60;

    if (minAgo < peak) {
      // Pre-peak: insulin building up
      var x1 = minAgo / 5 + 1;
      ret.iob = insulin * (1 - 0.001852 * x1 * x1 + 0.001852 * x1);
      ret.activity = sens * insulin * (2 / dia / 60 / peak) * minAgo;
    } else if (minAgo < 180) {
      // Post-peak: insulin declining
      var x2 = (minAgo - peak) / 5;
      ret.iob = insulin * (0.001323 * x2 * x2 - 0.054233 * x2 + 0.55556);
      ret.activity = sens * insulin * (2 / dia / 60 - (minAgo - peak) * 2 / dia / 60 / (60 * 3 - peak));
    }
    // After 180 minutes: IOB = 0
  }

  return ret;
}
```

### Insulin Curve Model

This is a **bilinear exponential decay** model:

| Phase | Time Range | IOB Formula |
|-------|------------|-------------|
| Pre-peak | 0 to 75 min | `insulin * (1 - 0.001852 * x1² + 0.001852 * x1)` |
| Post-peak | 75 to 180 min | `insulin * (0.001323 * x2² - 0.054233 * x2 + 0.55556)` |
| Depleted | > 180 min | `0` |

Where:
- `x1 = minAgo / 5 + 1`
- `x2 = (minAgo - peak) / 5`
- `scaleFactor = 3.0 / dia` (adjusts curve for different DIA)

### Activity Calculation

Activity represents the glucose-lowering effect rate:

```dart
// Units: BG (mg/dL) = (BG/U) * U insulin * scalar
ret.activity = sens * insulin * (2 / dia / 60 / peak) * minAgo;
```

**Code Reference**: `nr:lib/src/json_data.dart#L1409-L1440`

---

## COB Calculation

### Method: `calcCOB`

```dart
dynamic calcCOB(ProfileGlucData profile, DateTime time, int lastDecayedBy) {
  var delay = 20;  // 20 minute delay before absorption starts
  var isDecaying = false;
  var initialCarbs;

  if (carbs != null) {
    var carbTime = createdAt;
    
    var carbs_hr = profile.store.carbRatioPerHour;  // Default: 12g/hr
    if (carbs_hr == 0) carbs_hr = 12;
    var carbs_min = carbs_hr / 60;

    var decayedBy = carbTime;
    var minutesleft = (lastDecayedBy - carbTime.millisecondsSinceEpoch) / 1000 ~/ 60;
    decayedBy = decayedBy.add(Duration(
        minutes: math.max(delay, minutesleft) + carbs ~/ carbs_min));
    
    if (delay > minutesleft) {
      initialCarbs = carbs;
    } else {
      initialCarbs = carbs + minutesleft * carbs_min;
    }
    
    var startDecay = carbTime.add(Duration(minutes: delay));
    if (time.millisecondsSinceEpoch < lastDecayedBy ||
        time.millisecondsSinceEpoch > startDecay.millisecondsSinceEpoch) {
      isDecaying = true;
    } else {
      isDecaying = false;
    }

    return {
      'initialCarbs': initialCarbs, 
      'decayedBy': decayedBy, 
      'isDecaying': isDecaying, 
      'carbTime': carbTime
    };
  }
  return null;
}
```

### Carb Absorption Model

- **Delay**: 20 minutes before absorption starts
- **Rate**: `carbs_hr` (default 12g/hr) from profile
- **Linear decay**: Carbs decrease at constant rate after delay

### Total COB with Liver Sensitivity

```dart
void calcTotalCOB(ReportData data, DayData yesterday, dynamic ret, 
    ProfileGlucData profile, DateTime time, var iob) {
  
  var liverSensRatio = 8.0;  // TODO: tune this value
  var sens = profile.store.listSens.lastWhere(
      (e) => e.timeForCalc <= timeForCalc, orElse: () => null)?.value ?? 0.0;
  var carbRatio = profile.store.listCarbratio.lastWhere(
      (e) => e.timeForCalc <= timeForCalc, orElse: () => null)?.value ?? 0.0;
  
  var cCalc = calcCOB(profile, time, ret['lastDecayedBy']?.millisecondsSinceEpoch ?? 0);
  
  if (cCalc != null) {
    double decaysin_hr = (cCalc['decayedBy'].millisecondsSinceEpoch - 
        time.millisecondsSinceEpoch) / 1000 / 60 / 60;
    
    if (decaysin_hr > -10) {
      // Calculate delayed carbs based on insulin activity
      var actStart = iob(data, ret['lastDecayedBy'], yesterday).activity;
      var actEnd = iob(data, cCalc['decayedBy'], yesterday).activity;
      var avgActivity = (actStart + actEnd) / 2;
      
      // units: g = BG * scalar / BG / U * g / U
      var delayedCarbs = (avgActivity * liverSensRatio / sens) * carbRatio;
      int delayMinutes = delayedCarbs ~/ profile.store.carbRatioPerHour * 60;
      
      if (delayMinutes > 0) {
        cCalc['decayedBy'] = cCalc['decayedBy'].add(Duration(minutes: delayMinutes));
        decaysin_hr = (cCalc['decayedBy'].millisecondsSinceEpoch - 
            time.millisecondsSinceEpoch) / 1000 / 60 / 60;
      }
    }

    ret['lastDecayedBy'] = cCalc['decayedBy'];
    if (decaysin_hr > 0) {
      ret['totalCOB'] += math.min(carbs, decaysin_hr * profile.store.carbRatioPerHour);
      ret['isDecaying'] = cCalc['isDecaying'];
    }
  } else {
    ret['totalCOB'] = 0;
  }
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L1442-L1514`

---

## CalcIOBData and CalcCOBData Classes

### CalcIOBData

```dart
class CalcIOBData {
  double iob;           // Insulin remaining
  double activity;      // Current glucose-lowering rate
  TreatmentData lastBolus;
}
```

### CalcCOBData

```dart
class CalcCOBData {
  DateTime decayedBy;     // When COB will reach zero
  bool isDecaying;        // Whether actively absorbing
  int carbs_hr;           // Absorption rate
  double rawCarbImpact;   // Raw carb effect
  double cob;             // Current carbs on board
  TreatmentData lastCarbs;
}
```

---

## Time in Range (TIR) Calculations

### DayData Statistics

```dart
class DayData {
  int lowCount = 0;       // Readings below target
  int normCount = 0;      // Readings in target
  int highCount = 0;      // Readings above target
  int stdLowCount = 0;    // Readings below standard low (70)
  int stdNormCount = 0;   // Readings in standard range (70-180)
  int stdHighCount = 0;   // Readings above standard high (180)
  int entryCountValid = 0;
  int entryCountInvalid = 0;
  
  double min;             // Minimum glucose
  double max;             // Maximum glucose
  double mid;             // Mean glucose
  double varianz = 0.0;   // Variance
}
```

### Init Method - Calculating TIR

```dart
void init({DayData nextDay, bool keepProfile = false}) {
  min = 10000.0;
  max = -10000.0;
  mid = 0.0;
  entryCountValid = 0;
  entryCountInvalid = 0;
  normCount = 0;
  highCount = 0;
  lowCount = 0;
  stdNormCount = 0;
  stdHighCount = 0;
  stdLowCount = 0;
  carbCount = 0;
  carbs = 0;
  
  for (var entry in entries) {
    if (!entry.isGlucInvalid) {
      entryCountValid++;
      
      // Custom target range
      if (JsonData.isLow(entry.gluc, basalData.targetLow)) {
        lowCount++;
      } else if (JsonData.isHigh(entry.gluc, basalData.targetHigh)) {
        highCount++;
      } else {
        normCount++;
      }

      // Standard range (70-180)
      if (JsonData.isLow(entry.gluc, Globals.stdLow as double)) {
        stdLowCount++;
      } else if (JsonData.isHigh(entry.gluc, Globals.stdHigh as double)) {
        stdHighCount++;
      } else {
        stdNormCount++;
      }
      
      // Update min/max
      min = math.min(min, entry.gluc);
      max = math.max(max, entry.gluc);
    }
  }
}
```

### Range Check Methods

```dart
static bool isLow(double value, double low) {
  return value < low;
}

static bool isHigh(double value, double high) {
  return value >= high;  // Note: >= not >
}

static bool isNorm(double value, double low, double high) {
  return !JsonData.isLow(value, low) && !JsonData.isHigh(value, high);
}
```

**Important**: High is `>=` threshold, making it exclusive on the upper bound.

**Code Reference**: `nr:lib/src/json_data.dart#L2193-L2230`

---

## Average Glucose

```dart
double get avgGluc {
  var ret = 0.0;
  var count = 0;
  for (var entry in entries) {
    if (!entry.isGlucInvalid) {
      ret += entry.gluc;
      count++;
    }
  }
  return count > 0 ? ret / count : 0.0;
}
```

---

## Standard Deviation

```dart
double stdAbw(bool isMGDL) {
  var ret = math.sqrt(varianz);
  if (!isMGDL) ret = ret / 18.02;  // Convert to mmol/L
  return ret;
}
```

### Coefficient of Variation

```dart
double get varK => (mid ?? 0) != 0 ? stdAbw(true) / mid * 100 : 0;
```

CV = (Standard Deviation / Mean) × 100%

---

## Insulin Totals

### Bolus Categories

```dart
double get ieBolusSum {
  var ret = 0.0;
  for (var entry in treatments) {
    ret += (entry.bolusInsulin ?? 0);
  }
  return ret;
}

double get ieCorrectionSum {
  var ret = 0.0;
  for (var entry in treatments) {
    if (!entry.isCarbBolus && !entry.isSMB) {
      ret += entry.bolusInsulin;
    }
  }
  return ret;
}

double get ieCarbSum {
  var ret = 0.0;
  for (var entry in treatments) {
    if (entry.isCarbBolus && !entry.isSMB) {
      ret += entry.bolusInsulin;
    }
  }
  return ret;
}

double get ieSMBSum {
  var ret = 0.0;
  for (var entry in treatments) {
    if (entry.isSMB) ret += entry.bolusInsulin;
  }
  return ret;
}
```

### Basal Total

```dart
double ieBasalSum(bool useStore) {
  if (useStore) {
    return basalData.store.ieBasalSum;  // From profile
  }
  var ret = 0.0;
  for (var entry in profile) {
    ret += (entry.value ?? 0) * (entry.duration ?? 0) / 3600.0;
  }
  return ret;
}
```

### Zero Basal Duration

```dart
int get basalZeroDuration {
  var ret = 0;
  for (var entry in profile) {
    if (entry.value == 0 && entry.duration != null) {
      ret += entry.duration;
    }
  }
  return ret;  // Seconds of suspended basal
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L1975-L2038`

---

## Daily Averages

### Average Insulin Per Day

```dart
dynamic get avgInsulinPerDay {
  var ret = 0.0;
  var count = 0;
  var dayCount = 0;
  var lastTime = DateTime(2000);
  
  for (var entry in treatments) {
    if (entry.createdAt.isAfter(lastTime)) {
      dayCount++;
    }
    lastTime = DateTime(entry.createdAt.year, entry.createdAt.month, 
        entry.createdAt.day, 23, 59, 59);
    
    if (entry.insulin > 0) {
      ret += entry.insulin;
      count++;
    }
  }
  return {'value': dayCount >= 1 ? ret / dayCount : 0.0};
}
```

### Average Carbs Per Day

```dart
dynamic get avgCarbsPerDay {
  var ret = 0.0;
  var count = 0;
  var dayCount = 0;
  var lastTime = DateTime(2000);
  
  for (var entry in treatments) {
    if (entry.createdAt.isAfter(lastTime)) {
      dayCount++;
    }
    lastTime = DateTime(entry.createdAt.year, entry.createdAt.month, 
        entry.createdAt.day, 23, 59, 59);
    
    if (entry.carbs > 0) {
      ret += entry.carbs;
      count++;
    }
  }
  return {'value': dayCount >= 1 ? ret / dayCount : 0.0};
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L1906-L1952`

---

## Profile Basal with Temp Basals

The `profile` getter on DayData merges scheduled basal with temp basals:

```dart
List<ProfileEntryData> get profile {
  if (_profile != null) return _profile;
  _profile = <ProfileEntryData>[];
  
  // Start with scheduled basal
  for (var entry in basalData.store.listBasal) {
    var temp = ProfileEntryData(basalData.store.timezone, entry.time(date, true));
    temp.value = entry.value;
    temp.orgValue = entry.value;
    _profile.add(temp);
  }
  
  // Add temp basal treatments
  for (var t in treatments) {
    if (!t.isTempBasal) continue;
    var entry = ProfileEntryData.fromTreatment(basalData.store.timezone, t);
    entry.value = null;  // Mark for calculation
    _profile.add(entry);
  }
  
  // Sort and calculate adjusted values
  _profile.sort((a, b) => a.time(date).compareTo(b.time(date)));
  
  for (var i = 0; i < _profile.length; i++) {
    var entry = _profile[i];
    if (entry.value == null) {
      entry.value = entry.adjustedValue(last.orgValue);
      // ... handle overlaps and gaps
    }
  }
  
  return _profile;
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L2063-L2191`

---

## StatisticData Class

```dart
class StatisticData {
  double low;
  double high;
  double mid;
  int count;
  double varianz;
  double stdAbw;
  double get varK;  // Coefficient of variation
}
```

---

## Cross-References

- [data-models.md](data-models.md) - DayData, TreatmentData fields
- [profile-handling.md](profile-handling.md) - Profile settings for calculations
- [mapping/loop/insulin-math.md](../loop/insulin-math.md) - Loop's IOB approach for comparison

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial extraction from json_data.dart |
