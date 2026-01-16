# Nightscout Reporter: Unit Conversion

This document describes how Nightscout Reporter handles glucose unit conversion between mg/dL and mmol/L.

---

## Overview

Nightscout and AID systems may store glucose values in either mg/dL or mmol/L. Reporter provides flexible unit handling including:

1. Detection of server units from status
2. User preference for display units
3. Conversion between units
4. Precision management for display

---

## Conversion Factor

The standard conversion factor:

```dart
double get glucFactor => glucMGDL ? 1 : 18.02;
```

- **mg/dL to mmol/L**: `value / 18.02`
- **mmol/L to mg/dL**: `value * 18.02`

The factor 18.02 comes from the molecular weight of glucose (180.16 g/mol) divided by 10.

---

## Unit Detection

### From Server Status

```dart
bool isMGDL(StatusData status) {
  var check = status.settings.units?.trim()?.toLowerCase() ?? '';
  return check.startsWith('mg') && check.endsWith('dl');
}

void setGlucMGDL(StatusData status) {
  glucMGDLFromStatus = isMGDL(status);
}
```

The detection parses strings like:
- `"mg/dL"` → mg/dL
- `"mg/dl"` → mg/dL  
- `"mmol/L"` → mmol/L
- `"mmol"` → mmol/L

**Code Reference**: `nr:lib/src/globals.dart#L192-L199`

---

## User Preference

### Unit Selection Options

```dart
static String get msgUnitMGDL => Intl.message('mg/dL');
static String get msgUnitMMOL => Intl.message('mmol/L');
static String get msgUnitBoth => Intl.message('Beide');  // "Both" in German

List<String> listGlucUnits = [msgUnitMGDL, msgUnitMMOL, msgUnitBoth];

int glucMGDLIdx;  // 0 = mg/dL, 1 = mmol/L, 2 = Both
```

### Unit Getters

```dart
bool get glucMGDL => [true, false, true][glucMGDLIdx ?? 0];
bool get showBothUnits => glucMGDLIdx == 2;
```

When `showBothUnits` is true, both units are displayed in reports.

---

## Value Conversion

### For Saved Unit Values

When the server stores values in a different unit than the user prefers:

```dart
double glucForSavedUnitValue(double value) {
  if (glucMGDL == glucMGDLFromStatus) return value;  // Same units, no conversion
  if (glucMGDL) return value * 18.02;  // Convert mmol → mg/dL
  return value / 18.02;                 // Convert mg/dL → mmol
}
```

---

## Precision Handling

### Display Precision

```dart
double get glucPrecision => glucMGDL ? 0 : 2;
```

- **mg/dL**: Integer values (0 decimal places)
- **mmol/L**: 2 decimal places

### Standard Deviation Conversion

```dart
double stdAbw(bool isMGDL) {
  var ret = math.sqrt(varianz);
  if (!isMGDL) ret = ret / 18.02;  // Convert to mmol/L
  return ret;
}
```

---

## Treatment Unit Detection

For treatment glucose values that may come with their own unit indicator:

```dart
// In TreatmentData.fromJson():
if (json['units'] != null) {
  if (json['units'].toLowerCase() == Settings.msgUnitMGDL.toLowerCase() &&
      g.getGlucInfo()['unit'] == Settings.msgUnitMMOL) {
    ret.glucose = ret.glucose / 18.02;  // Server sent mg/dL, user wants mmol
  } else if (json['units'].toLowerCase() == Settings.msgUnitMMOL.toLowerCase() &&
      g.getGlucInfo()['unit'] == Settings.msgUnitMGDL) {
    ret.glucose = ret.glucose * 18.02;  // Server sent mmol, user wants mg/dL
  }
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L1373-L1381`

---

## Global Adjust Factor

A global adjustment factor can be applied to all glucose values:

```dart
double get gluc {
  return isGap ? -1 : Globals.adjustFactor * (type == 'sgv' ? sgv : rawbg) ?? 0;
}
```

This allows for global calibration adjustments if needed.

---

## Standard Thresholds

Reporter uses standard clinical thresholds:

```dart
// In Globals
static int stdLow = 70;   // mg/dL - standard low threshold
static int stdHigh = 180; // mg/dL - standard high threshold
```

These are always in mg/dL internally; conversion happens at display time.

---

## Profile Target Thresholds

Targets from the Nightscout status settings:

```dart
class ThresholdData {
  int bgHigh;         // Urgent high (e.g., 260)
  int bgTargetTop;    // Target ceiling (e.g., 180)
  int bgTargetBottom; // Target floor (e.g., 70)
  int bgLow;          // Urgent low (e.g., 55)
}
```

### With HbA1c Adjustment

Users can adjust targets based on their HbA1c goals:

```dart
int get bgTargetTop {
  if (thresholds == null) return null;
  var factor = Globals().user.adjustTarget ? Globals().user.hba1cAdjustFactor : 1.0;
  return (factor * thresholds.bgTargetTop).floor();
}

int get bgTargetBottom {
  if (thresholds == null) return null;
  var factor = Globals().user.adjustTarget ? Globals().user.hba1cAdjustFactor : 1.0;
  return (factor * thresholds.bgTargetBottom).floor();
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L149-L159`

---

## Basal Rate Precision

Profile basal rates track their precision:

```dart
int maxPrecision = 0;

// When parsing basal entries:
for (dynamic entry in json['basal']) {
  ret.listBasal.add(ProfileEntryData.fromJson(entry, ret.timezone, timeshift, percentage));
  ret.maxPrecision = math.max(ret.maxPrecision, Globals.decimalPlaces(ret.listBasal.last.value));
}
```

This ensures basal rates display with appropriate precision (e.g., 0.025 U/hr vs 1.5 U/hr).

---

## Display Formatting

### Date Formats by Locale

```dart
String get dateformat => Intl.message('dd.MM.yyyy',
    desc: 'this is the dateformat, please use dd for days, ' +
        'MM for months and yyyy for year. ' +
        'It has to be the english formatstring.');

String get dateShortFormat => Intl.message('dd.MM.');
```

### 12/24 Hour Format by Locale

```dart
bool get is24HourFormat {
  switch (code) {
    case 'en-US':
    case 'en-GB':
      return false;
    default:
      return true;
  }
}
```

---

## Alignment Implications

### Unit Ambiguity

Nightscout data can have unit ambiguity:

1. **Status units** - Server-level default
2. **Profile units** - Per-profile setting
3. **Treatment units** - Per-record override
4. **Entry values** - Typically match status

### Recommendation

For alignment, consider:

1. Always store values in mg/dL internally
2. Store original unit in metadata
3. Convert at display/export time
4. Handle the 18.02 factor consistently

### Unit Fields in NS

| Collection | Unit Field | Location |
|------------|-----------|----------|
| status | `settings.units` | Server default |
| profile | `units` | Per profile |
| treatments | `units` | Optional per-record |
| entries | (none) | Uses status default |

---

## Cross-References

- [data-models.md](data-models.md) - Field mappings
- [calculations.md](calculations.md) - Stats that need unit conversion
- [profile-handling.md](profile-handling.md) - Profile unit settings
- [mapping/nightscout/data-collections.md](../nightscout/data-collections.md) - NS unit fields

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial extraction from globals.dart and json_data.dart |
