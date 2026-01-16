# Nightscout Reporter Data Models

This document maps Nightscout Reporter's Dart data classes to Nightscout collections, showing how a consumer application interprets the canonical data model.

---

## Source File

All data models are defined in:
```
nr:lib/src/json_data.dart (2869 lines)
```

---

## EntryData → entries Collection

Represents glucose readings from CGM.

### Field Mapping

| Dart Field | NS Field | Type | Transformation |
|------------|----------|------|----------------|
| `id` | `_id` | String | Direct |
| `time` | `date` | DateTime | `JsonData.toDate()` - epoch ms to DateTime |
| `rssi` | `rssi` | int | Signal strength |
| `device` | `device` | String | Device identifier |
| `direction` | `direction` | String | Trend arrow |
| `rawbg` | `rawbg` | double | Raw BG value |
| `sgv` | `sgv` | double | Sensor glucose value |
| `mbg` | `mbg` | double | Manual BG (fingerstick) |
| `type` | `type` | String | "sgv", "mbg", "cal" |
| `slope` | `slope` | double | Calibration slope |
| `intercept` | `intercept` | double | Calibration intercept |
| `scale` | `scale` | double | Calibration scale |

### Computed Properties

```dart
bool get isGap => sgv < 20 || sgv > 1000;  // Gap detection

double get gluc => isGap ? -1 : Globals.adjustFactor * (type == 'sgv' ? sgv : rawbg);

double get bloodGluc => type == 'mbg' ? mbg : 0;  // Fingerstick only

double get fullGluc => isGap ? -1 : (type == 'mbg' ? mbg : gluc);

bool get isGlucInvalid => gluc == null || gluc <= 0;
```

### Validation Rules

1. **Gap Detection**: SGV < 20 or > 1000 = gap (sensor error)
2. **Type Inference**: If `type` is null but `sgv > 0`, set `type = 'sgv'`
3. **Unit Adjustment**: `Globals.adjustFactor` applies user's unit preference

### Code Reference
```
nr:lib/src/json_data.dart#L1516-L1602
```

---

## TreatmentData → treatments Collection

Represents all therapy events and interventions.

### Field Mapping

| Dart Field | NS Field | Type | Notes |
|------------|----------|------|-------|
| `id` | `_id` | String | MongoDB ObjectId |
| `eventType` | `eventType` | String | Treatment category |
| `duration` | `duration` | int | Duration in **seconds** (converted from NS minutes: `* 60`) |
| `createdAt` | `created_at` | DateTime | Event timestamp |
| `enteredBy` | `enteredBy` | String | Source identifier |
| `NSClientId` | `NSCLIENT_ID` | String | NS client identifier |
| `_carbs` | `carbs` | double | Carbohydrates (grams) |
| `insulin` | `insulin` | double | Bolus insulin (units) |
| `microbolus` | `microbolus` | double | SMB amount (units) |
| `splitExt` | `splitExt` | int | Extended bolus % |
| `splitNow` | `splitNow` | int | Immediate bolus % |
| `isSMB` | `isSMB` | bool | Super Micro Bolus flag |
| `pumpId` | `pumpId` | String | Pump-side identifier |
| `glucose` | `glucose` | double | BG at time of treatment |
| `glucoseType` | `glucoseType` | String | "Finger", "Sensor" |
| `notes` | `notes` | String | Free-form notes |
| `reason` | `reason` | String | Override/target reason |
| `targetTop` | `targetTop` | double | Temp target high |
| `targetBottom` | `targetBottom` | double | Temp target low |
| `_percent` | `percent` | int | Temp basal % adjustment |
| `_absolute` | `absolute` | double | Absolute temp basal rate |
| `_rate` | `rate` | double | Basal rate |
| `boluscalc` | `boluscalc` | BoluscalcData | Wizard calculation details |
| `insulinInjections` | `insulinInjections` | List | MDI injection records |

### Event Type Classification

```dart
String get _t => eventType.toLowerCase();

bool get isSiteChange => _t == 'site change';
bool get isInsulinChange => _t == 'insulin change';
bool get isSensorChange => _t == 'sensor change' || _t == 'sensor start';
bool get isPumpBatteryChange => _t == 'pump battery change';
bool get isProfileSwitch => _t == 'profile switch';
bool get isTempTarget => _t == 'temporary target';
bool get isTempBasal => _t == 'temp basal';
bool get isExercise => _t == 'exercise';
bool get isBGCheck => _t == 'bg check';
bool get isMealBolus => _t == 'meal bolus';
bool get isBolusWizard => _t == 'bolus wizard';
bool get isTempOverride => _t == 'temporary override';
bool get hasNoType => _t == '<none>' || _t == '';
```

### Uploader Detection

```dart
Uploader get from {
  if (_from == Uploader.Unknown) {
    var check = enteredBy.toLowerCase() ?? '';
    if (check == 'openaps') {
      _from = Uploader.OpenAPS;
    } else if (check == 'tidepool') {
      _from = Uploader.Tidepool;
    } else if (check.contains('androidaps')) {
      _from = Uploader.AndroidAPS;
    } else if (check.startsWith('xdrip')) {
      _from = Uploader.XDrip;
    } else if (check == 'spike') {
      _from = Uploader.Spike;
    }
  }
  return _from;
}
```

### Blood Glucose Detection

```dart
bool get isBloody => 
    glucoseType?.toLowerCase() == 'finger' || 
    eventType.toLowerCase() == 'bg check';
```

### Carb Handling

```dart
double get carbs => (_carbs != null && !isECarb) ? _carbs : 0.0;
double get eCarbs => isECarb ? _carbs : 0.0;  // Extended carbs (for slow absorption)

bool get isCarbBolus => isMealBolus || (isBolusWizard && carbs > 0);
```

### Temp Basal Value Resolution

```dart
double adjustedValue(double baseRate) {
  if (_percent != null) return baseRate + (baseRate * _percent) / 100.0;
  if (_rate != null) return _rate;
  return baseRate;
}
```

### Duration Conversion

**Important**: Nightscout stores duration in **minutes**, but Reporter converts to **seconds** during parsing:

```dart
ret.duration = JsonData.toInt(json['duration']) * 60; // duration is saved in minutes
```

### Code Reference
```
nr:lib/src/json_data.dart#L1132-L1514
```

---

## ProfileData → profile Collection

Represents therapy profile with time-based settings.

### Document Structure

| Dart Field | NS Field | Type |
|------------|----------|------|
| `id` | `_id` | String |
| `defaultProfile` | `defaultProfile` | String |
| `startDate` | `startDate` | DateTime |
| `duration` | `duration` | int |
| `store` | `store` | Map<String, ProfileStoreData> |
| `currentProfile` | `currentProfile` | String |

### ProfileStoreData (Individual Profile)

| Dart Field | NS Field | Type | Notes |
|------------|----------|------|-------|
| `name` | (key) | String | Profile name |
| `dia` | `dia` | double | Duration of Insulin Action (hours) |
| `carbsHr` | `carbs_hr` | int | Carb absorption rate (g/hr) |
| `delay` | `delay` | int | Insulin delay (minutes) |
| `timezone` | `timezone` | ProfileTimezone | IANA timezone |
| `startDate` | `startDate` | DateTime | When profile became active |
| `units` | `units` | String | "mg/dL" or "mmol/L" |
| `listCarbratio` | `carbratio` | List<ProfileEntryData> | I:C ratios by time |
| `listSens` | `sens` | List<ProfileEntryData> | ISF by time |
| `listBasal` | `basal` | List<ProfileEntryData> | Basal rates by time |
| `listTargetLow` | `target_low` | List<ProfileEntryData> | Target low by time |
| `listTargetHigh` | `target_high` | List<ProfileEntryData> | Target high by time |

### ProfileEntryData (Time-Value Pair)

| Dart Field | NS Field | Transformation |
|------------|----------|----------------|
| `_time` | `time` | "HH:mm" parsed to DateTime |
| `value` | `value` | double |
| `timeAsSeconds` | `timeAsSeconds` | Seconds from midnight |
| `duration` | (calculated) | Seconds until next entry |

### Computed Totals

```dart
double get ieBasalSum => _listSum(listBasal);  // Total daily basal
double get icrSum => _listSum(listCarbratio);  // Sum of I:C ratios
double get isfSum => _listSum(listSens);        // Sum of ISF values

int get carbRatioPerHour => (carbsHr ?? 0) > 0 ? carbsHr : 12;  // Default 12g/hr
```

### Profile Hash (for Change Detection)

```dart
String get hash {
  var temp = '${dia}-${carbsHr}-${list2String(listCarbratio)}-${list2String(listBasal)}-'
      '${list2String(listSens)}-${list2String(listTargetHigh)}-${list2String(listTargetLow)}';
  return sha1.convert(utf8.encode(temp)).toString();
}
```

### Code Reference
```
nr:lib/src/json_data.dart#L498-L941
```

---

## DeviceStatusData → devicestatus Collection

Represents controller, pump, and uploader status.

### Field Mapping

| Dart Field | NS Field | Type |
|------------|----------|------|
| `device` | `device` | String |
| `createdAt` | `created_at` | DateTime |
| `openAPS` | `openaps` | LoopData |
| `loop` | `loop` | LoopData |
| `pump` | `pump` | PumpData |
| `uploader` | `uploader` | UploaderData |
| `xdripjs` | `xdripjs` | XDripJSData |

### LoopData (Controller Status)

```dart
class LoopData {
  IOBData iob;  // Contains iob, basaliob, activity, time
}
```

### IOBData

| Dart Field | NS Field | Type |
|------------|----------|------|
| `iob` | `iob` | double |
| `basalIob` | `basaliob` | double |
| `activity` | `activity` | double |
| `time` | `time` | DateTime |

### PumpData

| Dart Field | NS Field | Type |
|------------|----------|------|
| `clock` | `clock` | DateTime |
| `pumpBattery` | `pumpbattery` | PumpBatteryData |
| `reservoir` | `reservoir` | double |
| `pumpStatus` | `pumpstatus` | PumpStatusData |

### UploaderData

| Dart Field | NS Field | Type |
|------------|----------|------|
| `batteryVoltage` | `batteryVoltage` | double |
| `batteryPercentageRemaining` | `battery` | double |

### Code Reference
```
nr:lib/src/json_data.dart#L1821-L1844
```

---

## StatusData → status Endpoint

Server configuration and settings.

### Field Mapping

| Dart Field | NS Field | Type |
|------------|----------|------|
| `status` | `status` | String |
| `name` | `name` | String |
| `version` | `version` | String |
| `serverTime` | `serverTime` | DateTime |
| `serverTimeEpoch` | `serverTimeEpoch` | int |
| `apiEnabled` | `apiEnabled` | bool |
| `careportalEnabled` | `careportalEnabled` | bool |
| `boluscalcEnabled` | `boluscalcEnabled` | bool |
| `head` | `head` | String |
| `settings` | `settings` | SettingsData |
| `extendedSettings` | `extendedSettings` | ExtendedSettingsData |

### SettingsData

| Dart Field | NS Field | Notes |
|------------|----------|-------|
| `units` | `units` | "mg/dL" or "mmol/L" |
| `timeFormat` | `timeFormat` | 12 or 24 |
| `nightMode` | `nightMode` | Dark theme |
| `thresholds` | `thresholds` | BG thresholds |
| `enable` | `enable` | Enabled plugins list |

### ThresholdData

| Dart Field | NS Field | Default |
|------------|----------|---------|
| `bgHigh` | `bgHigh` | Urgent high threshold |
| `bgTargetTop` | `bgTargetTop` | Target ceiling |
| `bgTargetBottom` | `bgTargetBottom` | Target floor |
| `bgLow` | `bgLow` | Urgent low threshold |

### Code Reference
```
nr:lib/src/json_data.dart#L278-L316
```

---

## BoluscalcData → treatments.boluscalc

Bolus wizard calculation details embedded in treatment records.

### Field Mapping

| Dart Field | NS Field | Type |
|------------|----------|------|
| `profile` | `profile` | String |
| `notes` | `notes` | String |
| `eventTime` | `eventTime` | DateTime |
| `targetBGLow` | `targetBGLow` | int |
| `targetBGHigh` | `targetBGHigh` | int |
| `isf` | `isf` | int |
| `ic` | `ic` | int |
| `iob` | `iob` | double |
| `bolusIob` | `bolusIob` | double |
| `basalIob` | `basalIob` | double |
| `bg` | `bg` | int |
| `insulinBg` | `insulinBg` | double |
| `insulinCarbs` | `insulincarbs` | double |
| `carbs` | `carbs` | double |
| `cob` | `cob` | double |
| `insulin` | `insulin` | double |
| `trend` | `trend` | String |
| `ttUsed` | `ttused` | bool |

### Code Reference
```
nr:lib/src/json_data.dart#L943-L1065
```

---

## Aggregation Classes

### DayData

Daily container for glucose and treatment aggregation.

```dart
class DayData {
  Date date;
  ProfileGlucData basalData;
  
  // Glucose counts
  int lowCount, normCount, highCount;
  int stdLowCount, stdNormCount, stdHighCount;
  int entryCountValid, entryCountInvalid;
  
  // Glucose stats
  double min, max, mid;
  double varianz;
  
  // Treatment counts
  int carbCount;
  double carbs;
  
  // Lists
  List<EntryData> entries;
  List<TreatmentData> treatments;
  
  // Computed
  double get avgGluc;
  double stdAbw(bool isMGDL);
  double get varK => mid != 0 ? stdAbw(true) / mid * 100 : 0;
}
```

### StatisticData

```dart
class StatisticData {
  double low, high, mid;
  int count;
  double varianz;
  double stdAbw;
  double get varK;
}
```

### Code Reference
```
nr:lib/src/json_data.dart#L1865-L2417
```

---

## Type Coercion Utilities

Reporter's `JsonData` base class provides safe parsing:

```dart
static DateTime toDate(value) {
  if (value == null) return DateTime(0, 1, 1);
  if (value is int) return DateTime.fromMillisecondsSinceEpoch(value);
  if (value is double) return DateTime.fromMillisecondsSinceEpoch(value.toInt());
  return JsonData.toLocal(DateTime.tryParse(value)) ?? DateTime(0, 1, 1);
}

static double toDouble(value, [def = 0.0]) {
  if (value == null || value == 'NaN') return def;
  if (value is double || value is int) return value;
  return double.tryParse(value) ?? def;
}

static int toInt(value, [int def = 0]) {
  if (value == null) return def;
  if (value is int) return value;
  if (value is double) return value.toInt();
  if (value is String) return int.tryParse(value) ?? def;
  if (value is bool) return value ? def : 1 - def;
  return def;
}

static bool toBool(value, {bool ifEmpty = false}) {
  if (value == null) return ifEmpty;
  if (value is bool) return value;
  if (value is String) {
    if (ifEmpty != null && value == '') return ifEmpty;
    return (value == 'true' || value == 'yes');
  }
  return false;
}
```

### Code Reference
```
nr:lib/src/json_data.dart#L13-L96
```

---

## Cross-References

- [README.md](README.md) - Overview and architecture
- [uploader-detection.md](uploader-detection.md) - Source detection patterns
- [Nightscout Data Model](../../docs/10-domain/nightscout-data-model.md) - Authoritative NS schema

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial extraction from json_data.dart |
