# Nightscout Reporter: Treatment Classification

This document describes how Nightscout Reporter classifies treatments by `eventType` and handles edge cases in treatment data.

---

## Overview

Nightscout uses the `eventType` field to categorize treatments. Reporter provides boolean properties for common checks, enabling clean conditional logic in report generation.

---

## Event Type Properties

All classification is based on lowercase comparison:

```dart
String get _t => eventType.toLowerCase();
```

### Device Events

| Property | Event Type(s) | Purpose |
|----------|--------------|---------|
| `isSiteChange` | `"site change"` | Infusion set change |
| `isInsulinChange` | `"insulin change"` | Reservoir/cartridge change |
| `isSensorChange` | `"sensor change"`, `"sensor start"` | CGM sensor insertion |
| `isPumpBatteryChange` | `"pump battery change"` | Pump battery replacement |

```dart
bool get isSiteChange => _t == 'site change';
bool get isInsulinChange => _t == 'insulin change';
bool get isSensorChange => _t == 'sensor change' || _t == 'sensor start';
bool get isPumpBatteryChange => _t == 'pump battery change';
```

### Profile & Override Events

| Property | Event Type | Purpose |
|----------|-----------|---------|
| `isProfileSwitch` | `"profile switch"` | Active profile change |
| `isTempTarget` | `"temporary target"` | Temporary glucose target |
| `isTempOverride` | `"temporary override"` | Loop override activation |

```dart
bool get isProfileSwitch => _t == 'profile switch';
bool get isTempTarget => _t == 'temporary target';
bool get isTempOverride => _t == 'temporary override';
```

### Basal Events

| Property | Event Type | Purpose |
|----------|-----------|---------|
| `isTempBasal` | `"temp basal"` | Temporary basal rate |

```dart
bool get isTempBasal => _t == 'temp basal';
```

### Bolus Events

| Property | Event Type | Purpose |
|----------|-----------|---------|
| `isMealBolus` | `"meal bolus"` | Bolus for meal |
| `isBolusWizard` | `"bolus wizard"` | Calculator-assisted bolus |
| `isCarbBolus` | (computed) | Any bolus with carbs |

```dart
bool get isMealBolus => _t == 'meal bolus';
bool get isBolusWizard => _t == 'bolus wizard';
bool get isCarbBolus => isMealBolus || (isBolusWizard && carbs > 0);
```

### Observation Events

| Property | Event Type | Purpose |
|----------|-----------|---------|
| `isBGCheck` | `"bg check"` | Fingerstick blood glucose |
| `isExercise` | `"exercise"` | Activity record |

```dart
bool get isBGCheck => _t == 'bg check';
bool get isExercise => _t == 'exercise';
```

### Special Cases

| Property | Condition | Purpose |
|----------|-----------|---------|
| `hasNoType` | `"<none>"` or `""` | Missing/empty event type |

```dart
bool get hasNoType => _t == '<none>' || _t == '';
```

**Code Reference**: `nr:lib/src/json_data.dart#L1186-L1214`

---

## SMB (Super Micro Bolus) Detection

SMB is identified via a dedicated boolean field, not event type:

```dart
bool isSMB;
double microbolus;  // SMB amount in units

double get bolusInsulin {
  if (insulin != null) return insulin;
  return 0.0;
}
```

Note: `microbolus` is tracked separately from `insulin` to distinguish SMBs from manual boluses.

---

## Blood Glucose Source Detection

Distinguishing fingerstick from sensor readings:

```dart
bool get isBloody => 
    glucoseType?.toLowerCase() == 'finger' || 
    eventType.toLowerCase() == 'bg check';
```

This combines two detection methods:
1. `glucoseType == "finger"` - Explicit type field
2. `eventType == "bg check"` - Implied by event type

---

## Carb Handling

### Regular vs Extended Carbs

```dart
double _carbs;
bool isECarb = false;  // Extended/slow carbs flag

double get carbs => (_carbs != null && !isECarb) ? _carbs : 0.0;
double get eCarbs => isECarb ? _carbs : 0.0;
```

Extended carbs (eCarbs) represent slow-absorbing carbs that are handled differently in COB calculations.

### Carb Event Types

From source analysis, carbs appear in:
- `"meal bolus"` - Carbs with insulin
- `"bolus wizard"` - Calculator entry
- `"carb correction"` - Carbs without insulin (for low BG)
- `"carbs"` - Standalone carb entry
- `"<none>"` - Some xDrip entries

```dart
// Commented historical logic showing known carb event types:
// switch (eventType.toLowerCase()) {
//   case 'bolus wizard':
//   case 'meal bolus':
//   case 'carb correction':
//   case 'carbs':
//     if (_carbs != null && !isECarb) return _carbs;
//     break;
//   case '<none>':
//     if (enteredBy.startsWith('xdrip') && _carbs != null && !isECarb) return _carbs;
//     break;
// }
```

**Code Reference**: `nr:lib/src/json_data.dart#L1226-L1252`

---

## Combo Bolus Handling

For extended/combo boluses:

```dart
int splitExt;   // Extended portion percentage
int splitNow;   // Immediate portion percentage
```

These sum to 100 for a standard combo bolus (e.g., 60/40 split).

---

## Temp Basal Value Types

Temp basals can be expressed three ways:

```dart
int _percent;      // Percentage adjustment (+/- from scheduled)
double _absolute;  // Absolute rate (U/hr)
double _rate;      // Rate value

double get absoluteTempBasal => _absolute;

double adjustedValue(double baseRate) {
  if (_percent != null) return baseRate + (baseRate * _percent) / 100.0;
  if (_rate != null) return _rate;
  return baseRate;
}
```

### Priority

1. `_percent` - Calculate from base rate
2. `_rate` - Use directly
3. `_absolute` - Use directly (uploader-dependent, see uploader-detection.md)

---

## Temp Target Fields

```dart
double targetTop;     // Upper bound of temp target range
double targetBottom;  // Lower bound of temp target range
String reason;        // Reason text (e.g., "Eating Soon", "Activity")
```

---

## Duration Handling

**Important**: Nightscout stores duration in **minutes**, but Reporter converts to **seconds** during parsing:

```dart
int duration; // duration in seconds

// In TreatmentData.fromJson():
ret.duration = JsonData.toInt(json['duration']) * 60; // duration is saved in minutes
```

This is a critical detail for alignment - when reading from Nightscout, multiply by 60.

---

## Edge Cases

### Empty Event Types

xDrip sometimes creates treatments with `<none>` or empty event type:

```dart
bool get hasNoType => _t == '<none>' || _t == '';
```

These often contain valid carb or BG data but require special handling.

### Duplicate Detection

```dart
int duplicates = 1;  // Count of duplicate entries
```

Used to track merged duplicate treatments.

### Pump ID for Deduplication

```dart
String pumpId;  // Pump-side identifier for deduplication
```

---

## Event Type Reference Table

Complete mapping of known event types:

| Event Type | Category | Key Fields |
|------------|----------|------------|
| `BG Check` | Observation | `glucose`, `glucoseType` |
| `Meal Bolus` | Insulin+Carbs | `insulin`, `carbs` |
| `Correction Bolus` | Insulin | `insulin` |
| `Snack Bolus` | Insulin+Carbs | `insulin`, `carbs` |
| `Bolus Wizard` | Insulin | `insulin`, `boluscalc` |
| `Carb Correction` | Carbs | `carbs` |
| `Carbs` | Carbs | `carbs` |
| `Temp Basal` | Basal | `percent` or `absolute`, `duration` |
| `Temp Basal Start` | Basal | `percent` or `absolute`, `duration` |
| `Temp Basal End` | Basal | (marks end) |
| `Profile Switch` | Profile | `profile`, `duration` |
| `Temporary Target` | Override | `targetTop`, `targetBottom`, `duration`, `reason` |
| `Temporary Override` | Override | `duration`, `reason` |
| `Site Change` | Device | |
| `Insulin Change` | Device | |
| `Sensor Change` | Device | |
| `Sensor Start` | Device | |
| `Pump Battery Change` | Device | |
| `Exercise` | Activity | `duration` |
| `Note` | Annotation | `notes` |
| `Announcement` | Annotation | `notes` |
| `<none>` | Unknown | (varies by uploader) |

---

## Cross-References

- [data-models.md](data-models.md) - TreatmentData field mapping
- [uploader-detection.md](uploader-detection.md) - Source identification
- [calculations.md](calculations.md) - COB/IOB from treatments
- [mapping/nightscout/data-collections.md](../nightscout/data-collections.md) - NS treatment schema

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial extraction from json_data.dart |
