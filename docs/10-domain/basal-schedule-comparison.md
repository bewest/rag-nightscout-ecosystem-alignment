# Basal Schedule Comparison: Loop vs AAPS vs Trio vs oref0

> **Date**: 2026-01-30  
> **Status**: Complete  
> **Domain**: AID Algorithms / Profile

---

## Executive Summary

Basal rate schedules define the background insulin delivery pattern across a 24-hour period. While all systems conceptually support time-based basal rates, their **data structures, time formats, and Nightscout sync formats differ significantly**.

| Aspect | Loop/Trio | AAPS | oref0 | Nightscout |
|--------|-----------|------|-------|------------|
| Time Format | TimeInterval (seconds) | timeAsSeconds (int) | minutes (int) | "HH:MM" string |
| Rate Unit | U/hr (Double) | U/hr (Double) | U/hr (rate) | U/hr (value) |
| Schedule Type | DailyValueSchedule | ProfileValue[] | basalprofile_data | basal[] |
| Timezone | Embedded | Profile-level | Profile-level | Profile-level |

---

## 1. Loop/Trio: Swift Implementation

### Core Type

```swift
// loop:LoopKit/LoopKit/BasalRateSchedule.swift:12
public typealias BasalRateSchedule = DailyValueSchedule<Double>
```

### Schedule Item Structure

```swift
// loop:LoopKit/LoopKit/DailyValueSchedule.swift:13-20
public struct RepeatingScheduleValue<T> {
    public var startTime: TimeInterval  // Seconds from midnight
    public var value: T                  // U/hr for basal
}
```

### Key Characteristics

- **Time**: `TimeInterval` (seconds as Double from midnight)
- **Value**: `Double` representing U/hr
- **Timezone**: Stored in `DailySchedule.timeZone` property
- **Total calculation**: Sum of (duration × rate) across all segments

### Nightscout Sync (Loop)

```swift
// loop:NightscoutService/NightscoutServiceKit/Extensions/ProfileSet.swift:69-71
let basalSchedule = BasalRateSchedule(
    dailyItems: profile.basal.map { RepeatingScheduleValue(startTime: $0.offset, value: $0.value) },
    timeZone: profile.timeZone)
```

Loop reads Nightscout profile's `basal` array where:
- `offset` = seconds from midnight
- `value` = U/hr rate

---

## 2. AAPS: Kotlin Implementation

### Core Interface

```kotlin
// aaps:core/interfaces/src/main/kotlin/app/aaps/core/interfaces/profile/Profile.kt:51-56
fun getBasal(): Double  // Current basal at "now"
fun getBasal(timestamp: Long): Double  // Basal at specific time
fun getBasalTimeFromMidnight(timeAsSeconds: Int): Double  // By seconds offset
```

### Profile Value Structure

```kotlin
// aaps:core/interfaces/src/main/kotlin/app/aaps/core/interfaces/profile/Profile.kt:133
open class ProfileValue(var timeAsSeconds: Int, var value: Double)
```

### Array Access

```kotlin
// aaps:core/interfaces/src/main/kotlin/app/aaps/core/interfaces/profile/Profile.kt:128
fun getBasalValues(): Array<ProfileValue>
```

### Key Characteristics

- **Time**: `timeAsSeconds` (Int, seconds from midnight)
- **Value**: `Double` representing U/hr
- **Pump constraints**: `basalStep`, `basalMinimumRate`, `basalMaximumRate` in PumpDescription
- **30-min profiles**: Some pumps support 30-min basal rate granularity (`is30minBasalRatesCapable`)

### Pump Capabilities

```kotlin
// aaps:core/data/src/main/kotlin/app/aaps/core/data/pump/defs/PumpDescription.kt:22-25
var isSetBasalProfileCapable = false
var basalStep = 0.0        // e.g., 0.01 U/hr
var basalMinimumRate = 0.0 // e.g., 0.04 U/hr
var basalMaximumRate = 0.0 // e.g., 25.0 U/hr
```

---

## 3. oref0: JavaScript Implementation

### Basal Lookup

```javascript
// oref0:lib/profile/basal.js:6-30
function basalLookup (schedules, now) {
    var basalprofile_data = _.sortBy(schedules, function(o) { return o.i; });
    var basalRate = basalprofile_data[basalprofile_data.length-1].rate;
    var nowMinutes = nowDate.getHours() * 60 + nowDate.getMinutes();

    for (var i = 0; i < basalprofile_data.length - 1; i++) {
        if ((nowMinutes >= basalprofile_data[i].minutes) && 
            (nowMinutes < basalprofile_data[i + 1].minutes)) {
            basalRate = basalprofile_data[i].rate;
            break;
        }
    }
    return Math.round(basalRate*1000)/1000;
}
```

### Schedule Item Structure

```javascript
// oref0 expects:
{
    i: 0,           // Index for sorting
    minutes: 0,     // Minutes from midnight
    rate: 0.8       // U/hr
}
```

### Key Characteristics

- **Time**: `minutes` (integer, minutes from midnight)
- **Value**: `rate` in U/hr
- **Sorting**: Uses `i` index field for ordering
- **Precision**: Rounds to 3 decimal places

---

## 4. Nightscout Profile Format

### Profile Store Structure

```javascript
// ns:lib/profile/profileeditor.js:146
// ns:lib/api2/summary/basaldataprocessor.js:30
{
    basal: [
        { time: "00:00", value: 0.8 },
        { time: "06:00", value: 1.2 },
        { time: "12:00", value: 0.9 },
        { time: "22:00", value: 0.7 }
    ]
}
```

### Key Characteristics

- **Time**: `"HH:MM"` string format
- **Value**: U/hr as number
- **Timezone**: Stored at profile level (`timezone` field)
- **Conversion**: Must parse string to get minutes/seconds offset

### Profile Functions

```javascript
// ns:lib/profilefunctions.js:212-213
profile.getBasal = function getBasal (time, spec_profile) {
    return profile.getValueByTime(Number(time), 'basal', spec_profile);
};
```

---

## 5. Time Format Comparison

| System | Time Storage | Example 6:00 AM |
|--------|--------------|-----------------|
| Loop/Trio | TimeInterval (seconds) | 21600.0 |
| AAPS | timeAsSeconds (int) | 21600 |
| oref0 | minutes (int) | 360 |
| Nightscout | "HH:MM" string | "06:00" |

### Conversion Requirements

```
Nightscout → Loop:    parse("HH:MM") → hours*3600 + minutes*60
Nightscout → AAPS:    parse("HH:MM") → hours*3600 + minutes*60
Nightscout → oref0:   parse("HH:MM") → hours*60 + minutes
Loop → Nightscout:    format(seconds/3600, seconds%3600/60)
```

---

## 6. Temp Basal Handling

All systems support temporary basal overrides:

| System | Temp Basal Type | Duration Unit |
|--------|-----------------|---------------|
| Loop | Absolute U/hr | TimeInterval |
| AAPS | Absolute or Percent | minutes |
| oref0 | Absolute U/hr | minutes |
| Nightscout | Absolute or Percent | minutes |

### AAPS Temp Basal Entity

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/TemporaryBasal.kt:32
data class TemporaryBasal(
    var timestamp: Long,
    var duration: Long,        // milliseconds
    var rate: Double,          // U/hr or percent
    var isAbsolute: Boolean,   // true = U/hr, false = percent
    var type: Type
)
```

### Nightscout Temp Basal Treatment

```javascript
// ns:lib/profilefunctions.js:377-380
if (treatment && !isNaN(treatment.absolute) && treatment.duration > 0) {
    tempbasal = Number(treatment.absolute);
} else if (treatment && treatment.percent) {
    tempbasal = basal * (100 + treatment.percent) / 100;
}
```

---

## 7. Identified Gaps

### GAP-PROF-010: Time Format Inconsistency

**Description**: Nightscout uses "HH:MM" strings while controllers use numeric offsets.

**Impact**: Parsing errors, timezone confusion, off-by-one minute issues.

**Remediation**: Standardize on seconds-from-midnight with explicit timezone.

### GAP-PROF-011: 30-Minute Basal Rate Support

**Description**: AAPS supports 30-minute basal rate granularity (`is30minBasalRatesCapable`) but this isn't reflected in Nightscout profile schema.

**Impact**: Pumps with 30-min granularity may lose precision.

**Remediation**: Extend Nightscout profile to support sub-hourly time boundaries.

### GAP-PROF-012: Basal Rate Precision

**Description**: Different systems use different precision:
- Loop: Double (full precision)
- AAPS: basalStep constraint (e.g., 0.01 U/hr)
- oref0: 3 decimal places
- Nightscout: Arbitrary JS number

**Impact**: Rounding differences when syncing between systems.

**Remediation**: Document precision requirements in OpenAPI spec.

### GAP-SYNC-020: Basal Schedule Change Events

**Description**: No standardized event for "basal schedule was changed" across systems.

**Impact**: Schedule changes may not propagate consistently.

**Remediation**: Define profile change event type with before/after snapshots.

---

## 8. Requirements Extracted

### REQ-PROF-010: Basal Time Format

**Statement**: Controllers MUST convert Nightscout "HH:MM" time strings to numeric seconds-from-midnight using profile timezone.

**Rationale**: Ensures consistent interpretation across all systems.

**Verification**: Unit tests with edge cases (midnight, DST transitions).

### REQ-PROF-011: Basal Rate Precision

**Statement**: Controllers SHOULD preserve basal rate precision to at least 0.01 U/hr during sync operations.

**Rationale**: Matches common pump step sizes.

**Verification**: Round-trip test: export → import → compare.

### REQ-PROF-012: Total Daily Basal Validation

**Statement**: Controllers SHOULD validate that total daily basal equals sum of (segment_duration × rate) for all 24 hours.

**Rationale**: Catches incomplete or malformed profiles.

**Verification**: Calculate TDD from profile, compare to sum.

---

## 9. Source Files Analyzed

| System | Key Files |
|--------|-----------|
| Loop | `LoopKit/LoopKit/BasalRateSchedule.swift`, `LoopKit/LoopKit/DailyValueSchedule.swift` |
| Loop Nightscout | `NightscoutService/NightscoutServiceKit/Extensions/ProfileSet.swift` |
| AAPS | `core/interfaces/.../profile/Profile.kt`, `database/impl/.../entities/TemporaryBasal.kt` |
| AAPS Pump | `core/data/.../pump/defs/PumpDescription.kt` |
| oref0 | `lib/profile/basal.js` |
| Nightscout | `lib/profilefunctions.js`, `lib/plugins/basalprofile.js`, `lib/profile/profileeditor.js` |

---

## 10. Terminology Mappings

| Concept | Loop | AAPS | oref0 | Nightscout |
|---------|------|------|-------|------------|
| Scheduled basal | BasalRateSchedule | Profile.getBasalValues() | basalprofile_data | profile.basal |
| Basal rate | value (Double) | value (Double) | rate | value |
| Time offset | startTime (seconds) | timeAsSeconds | minutes | time ("HH:MM") |
| Temp basal | TempBasal | TemporaryBasal | temp_basal | tempBasal treatment |
| Total daily | total() | baseBasalSum() | — | computed client-side |
