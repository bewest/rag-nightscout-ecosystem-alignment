# Nightscout Reporter: Profile Handling

This document describes how Nightscout Reporter handles profiles, including timezone management, time-based settings resolution, and profile mixing/switching.

---

## Overview

Profiles in Nightscout contain therapy settings that vary by time of day. Reporter implements sophisticated logic for:

1. Parsing profile documents from the API
2. Resolving time-based settings with timezone awareness
3. Handling profile switches and temporary overrides
4. Mixing profiles when settings change mid-day

---

## Profile Data Structure

### ProfileData (Document Level)

```dart
class ProfileData extends JsonData {
  String id;
  String defaultProfile;          // Name of active profile
  DateTime startDate;             // When this profile became active
  int duration;                   // Duration in seconds (0 = permanent)
  String currentProfile;          // Currently selected profile name
  Map<String, ProfileStoreData> store;  // Named profiles
}
```

### ProfileStoreData (Individual Profile)

```dart
class ProfileStoreData extends JsonData {
  String name;
  double dia;                              // Duration of Insulin Action (hours)
  int carbsHr;                             // Carb absorption rate (g/hr)
  int delay;                               // Insulin delay (minutes)
  ProfileTimezone timezone;                // IANA timezone
  DateTime startDate;                      // Profile effective date
  String units;                            // "mg/dL" or "mmol/L"
  int maxPrecision;                        // Max decimal places in basal
  
  List<ProfileEntryData> listCarbratio;    // I:C ratios by time
  List<ProfileEntryData> listSens;         // ISF by time
  List<ProfileEntryData> listBasal;        // Basal rates by time
  List<ProfileEntryData> listTargetLow;    // Target low by time
  List<ProfileEntryData> listTargetHigh;   // Target high by time
}
```

### ProfileEntryData (Time-Value Pair)

```dart
class ProfileEntryData extends JsonData {
  DateTime _time;           // Time of day (hour/minute/second)
  double value;             // Setting value
  int timeAsSeconds;        // Seconds from midnight
  int duration;             // Duration in seconds until next entry
  ProfileTimezone _timezone;
  
  // Temp basal adjustments
  double _percentAdjust;    // Percentage adjustment
  double _absoluteRate;     // Absolute rate override
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L357-L941`

---

## Timezone Handling

### ProfileTimezone Class

```dart
class ProfileTimezone {
  String name;              // IANA timezone name (e.g., "America/New_York")
  tz.Location location;     // Timezone location object
  int localDiff;            // Hour difference from local time

  ProfileTimezone(this.name, [bool isInitializing = false]) {
    location = tz.getLocation(name);
    if (location != null) {
      var d = tz.TZDateTime(location, 0, 1, 1, 0, 0, 0);
      localDiff = d.difference(DateTime(0)).inHours + JsonData.hourDiff;
    }
  }
}
```

### Time Resolution with Timezone

```dart
DateTime time(Date date, [bool adjustLocalForTime = false]) {
  var hour = _time.hour;
  if (adjustLocalForTime) hour += _timezone.localDiff;

  // Handle day wraparound
  while (hour < 0) hour += 24;
  while (hour >= 24) hour -= 24;

  return DateTime(date.year, date.month, date.day, hour, _time.minute, _time.second);
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L343-L355`

---

## Time-Based Settings Parsing

### From JSON

```dart
factory ProfileEntryData.fromJson(
    Map<String, dynamic> json, 
    ProfileTimezone timezone, 
    int timeshift,
    [double percentage = 1.0, bool isReciprocal = false]) {
  
  var ret = ProfileEntryData(timezone);
  if (json == null) return ret;
  
  ret._time = JsonData.toTime(json['time']);  // Parse "HH:mm" string
  
  // Apply timeshift
  if (ret._time.hour < 24 - timeshift) {
    ret._time = ret._time.add(Duration(hours: timeshift));
  } else {
    ret._time = ret._time.add(Duration(hours: timeshift - 24));
  }
  
  ret.value = JsonData.toDouble(json['value']);
  
  // Apply percentage adjustment
  if (ret.value != null) {
    if (isReciprocal) {
      // For ISF and I:C, higher percentage = lower value
      if (percentage > 0) ret.value /= percentage;
    } else {
      // For basal, higher percentage = higher rate
      ret.value *= percentage;
    }
  }
  
  ret.timeAsSeconds = JsonData.toInt(json['timeAsSeconds']);
  return ret;
}
```

### Duration Calculation

Entries don't have explicit duration—it's calculated from the gap to the next entry:

```dart
static void _adjustDuration(List<ProfileEntryData> list) {
  for (var i = 0; i < list.length; i++) {
    var end = 86400;  // End of day in seconds
    if (i < list.length - 1) {
      end = list[i + 1].timeForCalc;
    }
    list[i].duration = end - list[i].timeForCalc;
  }
}
```

### Midnight Entry Handling

If the first entry doesn't start at midnight, wrap the last entry:

```dart
static void _adjust(List<ProfileEntryData> list) {
  list.sort((a, b) => a._time.compareTo(b._time));
  
  if (list.isNotEmpty && list.first._time.hour != 0) {
    var first = list.last.copy;
    if (first.value == list.first.value) {
      // Same value, just extend the first entry back
      list.first._time = list.first._time.add(Duration(hours: -first._time.hour));
    } else {
      // Different value, insert copy at midnight
      first._time = first._time.add(Duration(hours: -first._time.hour));
      list.insert(0, first);
    }
  }
  _adjustDuration(list);
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L581-L610`

---

## Computed Totals

### Total Daily Basal

```dart
double get ieBasalSum => _listSum(listBasal);

double _listSum(List<ProfileEntryData> list) {
  var ret = 0.0;
  for (var entry in list) {
    ret += (entry.value ?? 0) * (entry.duration ?? 0) / 3600;
  }
  return ret;
}
```

This calculates: `Σ (rate × hours) = total units/day`

### Default Carb Absorption

```dart
int get carbRatioPerHour => (carbsHr ?? 0) > 0 ? carbsHr : 12;
```

Default: 12g carbs absorbed per hour.

---

## Profile Hashing

For change detection (has this profile actually changed?):

```dart
String get hash {
  var temp = '${dia}-${carbsHr}-${list2String(listCarbratio)}-${list2String(listBasal)}-'
      '${list2String(listSens)}-${list2String(listTargetHigh)}-${list2String(listTargetLow)}';
  var bytes = convert.utf8.encode(temp);
  return '${crypto.sha1.convert(bytes)}';
}

String list2String(List<ProfileEntryData> list) {
  var dst = <String>[];
  for (var entry in list) {
    dst.add(entry.hash);  // "HH:mm=value"
  }
  return dst.join('|');
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L537-L542`

---

## Profile Mixing

When a profile switch occurs mid-day, Reporter "mixes" the profiles:

### Mix Logic

```dart
void mixWith(ProfileData src) {
  for (var key in store.keys) {
    // Use same-named store, or default if not found
    var srcKey = key;
    if (!src.store.containsKey(srcKey)) srcKey = src.defaultProfile;

    if (src.store.containsKey(srcKey)) {
      // Remove settings after switch time
      store[key].removeFrom(
          src.startDate.hour, 
          src.startDate.minute, 
          src.startDate.second, 
          src.duration);
      // Add settings from new profile
      store[key].addFrom(src, src.store[srcKey]);
    }
  }
}
```

### Remove From Time

```dart
void removeFrom(int hour, int minute, int second, int duration) {
  _removeFrom(listCarbratio, hour * 3600 + minute * 60 + second, duration);
  _removeFrom(listSens, hour * 3600 + minute * 60 + second, duration);
  _removeFrom(listBasal, hour * 3600 + minute * 60 + second, duration);
  // ... etc for all lists
}
```

### Import From Time

```dart
void _importFromTime(DateTime time, List<ProfileEntryData> listSrc, List<ProfileEntryData> listDst) {
  var date = Date(time.year, time.month, time.day);
  listSrc = listSrc.where((p) => p.endTime(date).isAfter(time)).toList();
  if (listSrc.isEmpty) return;
  
  listDst = listDst.where((p) => p.time(date).isBefore(time)).toList();
  if (listDst.isEmpty) listDst.add(listSrc.last.copy);
  
  // Adjust durations at the boundary
  listDst.last.duration = time.difference(listDst.last.time(date)).inSeconds;
  listSrc.first.duration = time.difference(listSrc.first._time).inSeconds;
  listSrc.first._time = time;
  
  listDst.addAll(listSrc);
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L922-L941`

---

## Finding Settings at a Time

### ProfileGlucData

A helper class for resolving settings at a specific glucose reading time:

```dart
class ProfileGlucData {
  DateTime day;
  double targetLow = 70;
  double targetHigh = 180;
  ProfileEntryData sens;        // Active ISF
  ProfileEntryData carbRatio;   // Active I:C
  ProfileEntryData basal;       // Active basal rate
  ProfileStoreData store;

  ProfileEntryData find(Date date, DateTime time, List<ProfileEntryData> list) {
    var ret = ProfileEntryData(store.timezone);
    var check = DateTime(date.year, date.month, date.day, time.hour, time.minute, time.second);
    
    for (var entry in list) {
      if (!entry.time(date).isAfter(check)) {
        ret = entry;
      }
    }
    return ret;
  }
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L318-L341`

---

## Temp Basal in Profile Context

When a temp basal is active, ProfileEntryData tracks the adjustment:

```dart
double _percentAdjust;    // e.g., +50 for 150% temp
double _absoluteRate;     // e.g., 1.5 for absolute 1.5 U/hr

double get tempAdjusted =>
    _absoluteRate != null ? 0 : (orgValue == null || orgValue == 0 ? 0 : (value - orgValue) / orgValue);

bool get isCalculated => _percentAdjust != null || _absoluteRate != null;

double adjustedValue(double v) {
  if (_percentAdjust != null) return v + (v * _percentAdjust) / 100.0;
  if (_absoluteRate != null) return _absoluteRate;
  return v;
}
```

### From Treatment to Profile Entry

```dart
factory ProfileEntryData.fromTreatment(ProfileTimezone timezone, TreatmentData src) {
  var ret = ProfileEntryData(timezone, src.createdAt);
  
  if (src._percent != null) {
    ret.percentAdjust = src._percent.toDouble();
  } else if (src._rate != null) {
    ret.absoluteRate = src._rate;
  }

  ret.from = src.from;
  
  // Uploader-specific handling
  if ((src.from == Uploader.Minimed600 ||
          src.from == Uploader.Tidepool ||
          src.from == Uploader.Spike ||
          src.from == Uploader.Unknown) &&
      src._absolute != null) {
    ret.absoluteRate = src._absolute;
  }
  
  ret.duration = src.duration;
  return ret;
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L454-L469`

---

## Units Handling

### Unit Detection from Status

```dart
bool isMGDL(StatusData status) {
  var check = status.settings.units?.trim()?.toLowerCase() ?? '';
  return check.startsWith('mg') && check.endsWith('dl');
}

void setGlucMGDL(StatusData status) {
  glucMGDLFromStatus = isMGDL(status);
}
```

### Unit-Aware Target Retrieval

```dart
int get bgTargetTop {
  if (thresholds == null) return null;
  var factor = Globals().user.adjustTarget ? Globals().user.hba1cAdjustFactor : 1.0;
  return (factor * thresholds.bgTargetTop).floor();
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L149-L159` (in SettingsData)

---

## Reference Timezone

A default timezone for fallback:

```dart
static String refTimezone = 'Europe/Berlin';

ProfileTimezone(this.name, [bool isInitializing = false]) {
  try {
    location = tz.getLocation(name);
  } catch (ex) {
    location = tz.getLocation(Globals.refTimezone);
  }
}
```

**Code Reference**: `nr:lib/src/globals.dart`

---

## Cross-References

- [data-models.md](data-models.md) - ProfileData field mapping
- [unit-conversion.md](unit-conversion.md) - mg/dL vs mmol/L handling
- [calculations.md](calculations.md) - Using profiles for IOB/COB
- [mapping/nightscout/data-collections.md](../nightscout/data-collections.md) - NS profile schema

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial extraction from json_data.dart |
