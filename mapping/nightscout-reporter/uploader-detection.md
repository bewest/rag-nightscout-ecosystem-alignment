# Nightscout Reporter: Uploader Detection

This document describes how Nightscout Reporter identifies the source of data (which AID controller or app uploaded it) by parsing the `enteredBy` field in treatments.

---

## Overview

Nightscout doesn't have a standardized field for identifying the data source. Different uploaders populate the `enteredBy` field with varying formats. Reporter uses pattern matching to detect the source.

## Uploader Enum

```dart
enum Uploader { 
  Unknown,      // Default/unrecognized
  XDrip,        // xDrip+ Android app
  Tidepool,     // Tidepool uploader
  Minimed600,   // Medtronic 600 series
  OpenAPS,      // oref0/oref1 rigs
  AndroidAPS,   // AAPS
  Spike         // Spike iOS app
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L11`

---

## Detection Logic

The detection is performed lazily (cached after first access) in the `from` getter:

```dart
Uploader _from = Uploader.Unknown;

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

**Code Reference**: `nr:lib/src/json_data.dart#L1166-L1184`

---

## Detection Patterns

| Uploader | Pattern | Match Type | Example `enteredBy` Values |
|----------|---------|------------|---------------------------|
| **OpenAPS** | `== "openaps"` | Exact (lowercase) | `"openaps"` |
| **Tidepool** | `== "tidepool"` | Exact (lowercase) | `"tidepool"` |
| **AndroidAPS** | `.contains("androidaps")` | Substring | `"AndroidAPS"`, `"AAPS-AndroidAPS"` |
| **xDrip** | `.startsWith("xdrip")` | Prefix | `"xdrip"`, `"xDrip+"`, `"xdrip-js"` |
| **Spike** | `== "spike"` | Exact (lowercase) | `"spike"` |
| **Minimed600** | Special handling | Via `_key600` | (key field presence) |
| **Unknown** | (default) | Fallback | Any unrecognized value |

---

## Special Handling: Minimed600

Medtronic 600 series pumps have a unique identification pattern using a key field:

```dart
String _key600;
String get key600 => _key600 ?? '';
```

The Minimed600 uploader is also detected in temp basal handling:

```dart
factory ProfileEntryData.fromTreatment(ProfileTimezone timezone, TreatmentData src) {
  // ...
  if ((src.from == Uploader.Minimed600 ||
          src.from == Uploader.Tidepool ||
          src.from == Uploader.Spike ||
          src.from == Uploader.Unknown) &&
      src._absolute != null) {
    ret.absoluteRate = src._absolute;
  }
  // ...
}
```

**Code Reference**: `nr:lib/src/json_data.dart#L454-L469`

---

## Usage in Reporter

Uploader detection affects:

### 1. Temp Basal Rate Resolution

Different uploaders send temp basal data differently:

```dart
factory ProfileEntryData.fromTreatment(ProfileTimezone timezone, TreatmentData src) {
  var ret = ProfileEntryData(timezone, src.createdAt);
  
  if (src._percent != null) {
    ret.percentAdjust = src._percent.toDouble();
  } else if (src._rate != null) {
    ret.absoluteRate = src._rate;
  }

  ret.from = src.from;
  
  // Special handling for uploaders that use absolute rate differently
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

### 2. Duration Interpretation

Some uploaders express duration differently. Spike in particular calculates rates over duration:

```dart
// spike needs a special handling, since the value seems to be the amount
// given over the duration, not the amount given in one hour.
// if (from == Uploader.Spike) return _absoluteRate / (duration / 3600);
```

(Commented out in source, but documents the known difference)

---

## Alignment Implications

### Missing Standard Field

The lack of a standardized `source` or `uploader` field in Nightscout means:

1. Detection is heuristic-based and fragile
2. New uploaders may not be recognized
3. Custom `enteredBy` values cause Unknown classification

### Proposed Alignment

Consider a canonical `source` field:

```json
{
  "source": {
    "type": "controller",
    "name": "AndroidAPS",
    "version": "3.2.0",
    "device": "Pixel 7"
  }
}
```

### Current Workarounds

Uploaders using different identification:

| Uploader | Identity Strategy |
|----------|------------------|
| AAPS | Uses `identifier` UUID |
| Loop | Uses `pumpId` + `pumpType` + `pumpSerial` composite |
| xDrip | Uses `uuid` |
| OpenAPS | Uses `enteredBy` = "openaps" |

---

## Known enteredBy Values

From analysis of various NS sites:

| `enteredBy` Value | Source |
|-------------------|--------|
| `"openaps"` | OpenAPS rig |
| `"AndroidAPS"` | AAPS |
| `"AAPS"` | AAPS (newer) |
| `"xDrip+"` | xDrip+ Android |
| `"xdrip"` | xDrip variants |
| `"xdrip-js"` | xDrip JavaScript bridge |
| `"spike"` | Spike iOS |
| `"tidepool"` | Tidepool uploader |
| `"Loop"` | Loop iOS (not detected by Reporter) |
| `"Trio"` | Trio (not detected by Reporter) |
| `"Nightscout"` | NS Careportal |
| Custom | User-entered via Careportal |

### Gap: Loop and Trio

Reporter doesn't explicitly detect Loop or Trio. They would fall into `Unknown`:

```dart
// Not in detection logic:
// } else if (check == 'loop') {
//   _from = Uploader.Loop;
// } else if (check == 'trio') {
//   _from = Uploader.Trio;
// }
```

This is a gap for alignment purposes.

---

## Practical Recommendations

### For Consumers

1. Always lowercase `enteredBy` before matching
2. Use substring matching for flexibility (`contains`)
3. Have a robust fallback for `Unknown`
4. Consider maintaining a mapping table that can be updated

### For Uploaders

1. Use consistent, identifiable `enteredBy` values
2. Include version info when possible: `"AndroidAPS 3.2.0"`
3. Consider adding structured source metadata

---

## Cross-References

- [data-models.md](data-models.md) - TreatmentData field mapping
- [treatment-classification.md](treatment-classification.md) - Event type handling
- [mapping/nightscout/data-collections.md](../nightscout/data-collections.md) - Core NS treatment fields

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial extraction from json_data.dart |
