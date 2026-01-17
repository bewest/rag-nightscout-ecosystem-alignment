# Profile/Therapy Settings: Cross-System Comparison

This document provides a unified comparison of how Loop, Trio, and AAPS represent and sync therapy settings (basal rates, ISF, CR, targets) to Nightscout. It addresses format differences, timezone handling, and profile switch semantics.

---

## Executive Summary

| Aspect | Loop | AAPS | Trio | Nightscout (Canonical) |
|--------|------|------|------|------------------------|
| **Profile Entity** | `TherapySettings` | `ProfileSwitch` | `FetchedNightscoutProfile` | `profile` collection |
| **Time Representation** | `TimeInterval` (seconds) | `Block` (duration-based) | `NightscoutTimevalue` | `time` + `timeAsSeconds` |
| **Timezone Storage** | `TimeZone` object per schedule | `utcOffset: Long` per entity | IANA string from NS | IANA string in profile |
| **Profile Switch** | Implicit (settings edited directly) | Explicit entity with modifiers | Implicit (NS-driven) | `Profile Switch` treatment |
| **Sync Direction** | Upload only (optional) | Bidirectional | Download only | N/A (hub) |
| **Override Mechanism** | `TemporaryScheduleOverride` | `ProfileSwitch.percentage/timeshift` | `Override` + `TempTarget` | `Temporary Override` treatment |

---

## 1. Profile Format Structure Comparison

### 1.1 Core Settings Fields

| Setting | Nightscout | Loop | AAPS | Trio |
|---------|------------|------|------|------|
| **Basal Rates** | `basal[]` | `BasalRateSchedule` | `basalBlocks: List<Block>` | `basal: [NightscoutTimevalue]` |
| **ISF (Sensitivity)** | `sens[]` | `InsulinSensitivitySchedule` | `isfBlocks: List<Block>` | `sens: [NightscoutTimevalue]` |
| **Carb Ratio** | `carbratio[]` | `CarbRatioSchedule` | `icBlocks: List<Block>` | `carbratio: [NightscoutTimevalue]` |
| **Target Low** | `target_low[]` | `GlucoseRangeSchedule` | `targetBlocks: List<TargetBlock>` | `target_low: [NightscoutTimevalue]` |
| **Target High** | `target_high[]` | `GlucoseRangeSchedule` | `targetBlocks: List<TargetBlock>` | `target_high: [NightscoutTimevalue]` |
| **Insulin Duration** | `dia` (hours) | `InsulinModel.effectDuration` | `insulinConfiguration.dia` | `dia` (hours) |
| **Glucose Units** | `units` string | `HKUnit` | `glucoseUnit: GlucoseUnit` | `units` string |
| **Timezone** | `timezone` (IANA) | `TimeZone` object | `utcOffset: Long` | `timezone` (IANA) |

### 1.2 Loop TherapySettings Structure

```swift
// Source: LoopKit/LoopKit/TherapySettings.swift
public struct TherapySettings: Equatable {
    public var glucoseTargetRangeSchedule: GlucoseRangeSchedule?
    public var correctionRangeOverrides: CorrectionRangeOverrides?
    public var overridePresets: [TemporaryScheduleOverridePreset]?
    public var maximumBasalRatePerHour: Double?
    public var maximumBolus: Double?
    public var suspendThreshold: GlucoseThreshold?
    public var insulinSensitivitySchedule: InsulinSensitivitySchedule?
    public var carbRatioSchedule: CarbRatioSchedule?
    public var basalRateSchedule: BasalRateSchedule?
    public var defaultRapidActingModel: ExponentialInsulinModelPreset?
}
```

**Key characteristics:**
- All schedules are optional (`?`)
- Uses `DailyQuantitySchedule<T>` with HealthKit units (`HKQuantity`)
- Includes safety limits (`maximumBasalRatePerHour`, `maximumBolus`, `suspendThreshold`)
- Override presets stored alongside therapy settings
- No explicit profile naming - settings are the profile

### 1.3 AAPS ProfileSwitch Structure

```kotlin
// Source: database/impl/src/main/kotlin/app/aaps/database/entities/ProfileSwitch.kt
data class ProfileSwitch(
    override var id: Long = 0,
    override var timestamp: Long,
    override var utcOffset: Long = TimeZone.getDefault().getOffset(timestamp).toLong(),
    
    var basalBlocks: List<Block>,
    var isfBlocks: List<Block>,
    var icBlocks: List<Block>,
    var targetBlocks: List<TargetBlock>,
    var glucoseUnit: GlucoseUnit,
    
    var profileName: String,
    var timeshift: Long,      // milliseconds
    var percentage: Int,      // 1-XXX (100 = normal)
    override var duration: Long  // milliseconds (0 = permanent, per NsIncomingDataProcessorTest.kt)
    
    var insulinConfiguration: InsulinConfiguration
) : TraceableDBEntry, DBEntryWithTimeAndDuration
```

**Key characteristics:**
- Event-based entity (each switch is a database record)
- Stores complete profile data at time of switch
- Includes modifiers (`percentage`, `timeshift`) for adjustments
- `duration` distinguishes temporary vs permanent switches
- `utcOffset` captures timezone at event time

### 1.4 Trio FetchedNightscoutProfile Structure

```swift
// Source: Trio/Sources/Models/FetchedProfile.swift
struct FetchedNightscoutProfile: JSON {
    let dia: Decimal
    let carbs_hr: Int
    let delay: Decimal
    let timezone: String          // IANA timezone
    let target_low: [NightscoutTimevalue]
    let target_high: [NightscoutTimevalue]
    let sens: [NightscoutTimevalue]
    let basal: [NightscoutTimevalue]
    let carbratio: [NightscoutTimevalue]
    let units: String
}

struct FetchedNightscoutProfileStore: JSON {
    let _id: String
    let defaultProfile: String
    let startDate: String
    let mills: Decimal
    let enteredBy: String
    let store: [String: ScheduledNightscoutProfile]
    let created_at: String
}
```

**Key characteristics:**
- Direct mirror of Nightscout schema
- Uses `NightscoutTimevalue` for time-based arrays
- Fetched from Nightscout, not locally authored
- `store` dictionary allows multiple named profiles

### 1.5 Nightscout Canonical Structure

```json
{
    "_id": "507f1f77bcf86cd799439011",
    "defaultProfile": "Default",
    "startDate": "2026-01-16T00:00:00.000Z",
    "mills": 1736985600000,
    "enteredBy": "Loop",
    "store": {
        "Default": {
            "basal": [
                {"time": "00:00", "value": 0.8, "timeAsSeconds": 0},
                {"time": "06:00", "value": 1.2, "timeAsSeconds": 21600}
            ],
            "sens": [
                {"time": "00:00", "value": 45, "timeAsSeconds": 0}
            ],
            "carbratio": [
                {"time": "00:00", "value": 10, "timeAsSeconds": 0}
            ],
            "target_low": [
                {"time": "00:00", "value": 100, "timeAsSeconds": 0}
            ],
            "target_high": [
                {"time": "00:00", "value": 120, "timeAsSeconds": 0}
            ],
            "timezone": "America/New_York",
            "dia": 5,
            "units": "mg/dl"
        }
    }
}
```

---

## 2. Time-Based Settings Representation

### 2.1 Time-Value Format Comparison

| System | Structure | Time Format | Example |
|--------|-----------|-------------|---------|
| **Nightscout** | `{time, timeAsSeconds, value}` | HH:MM string + seconds from midnight | `{"time": "06:00", "timeAsSeconds": 21600, "value": 1.2}` |
| **Loop** | `RepeatingScheduleValue<T>` | `TimeInterval` (seconds from midnight) | `RepeatingScheduleValue(startTime: 21600, value: 1.2)` |
| **AAPS** | `Block` | Duration-based segments (ms) | `Block(duration: 21600000, amount: 1.2)` |
| **Trio** | `NightscoutTimevalue` | Same as Nightscout | `NightscoutTimevalue(time: "06:00", value: 1.2, timeAsSeconds: 21600)` |

### 2.2 Loop DailyValueSchedule

```swift
// Source: LoopKit/LoopKit/DailyValueSchedule.swift
public struct RepeatingScheduleValue<T> {
    public var startTime: TimeInterval  // Seconds from midnight
    public var value: T
}

public struct DailyValueSchedule<T>: DailySchedule {
    let referenceTimeInterval: TimeInterval
    let repeatInterval: TimeInterval    // Always 24 hours
    public let items: [RepeatingScheduleValue<T>]
    public var timeZone: TimeZone
    
    func scheduleOffset(for date: Date) -> TimeInterval {
        let interval = date.timeIntervalSinceReferenceDate + 
                       TimeInterval(timeZone.secondsFromGMT(for: date))
        return ((interval - referenceTimeInterval)
                .truncatingRemainder(dividingBy: repeatInterval)) + referenceTimeInterval
    }
}
```

**Key insight:** Loop applies timezone adjustment when calculating `scheduleOffset`, ensuring the schedule is interpreted in the user's local timezone.

### 2.3 AAPS Block-Based Schedule

```kotlin
// AAPS uses duration-based blocks rather than start times
data class Block(
    val duration: Long,  // Duration in milliseconds
    val amount: Double   // Value for this block
)

data class TargetBlock(
    val duration: Long,
    val lowTarget: Double,
    val highTarget: Double
)
```

**Key insight:** AAPS blocks define *duration* of each segment, not start time. To convert:
- Nightscout `timeAsSeconds` → cumulative duration from previous segments
- Block 1: 0-6h = 21600000ms, Block 2: 6h-15h = 32400000ms

### 2.4 Nightscout Time Processing

```javascript
// Source: cgm-remote-monitor/lib/profilefunctions.js
profile.timeStringToSeconds = function timeStringToSeconds(time) {
    var split = time.split(':');
    return parseInt(split[0]) * 3600 + parseInt(split[1]) * 60;
};

profile.getValueByTime = function getValueByTime(time, valueType, spec_profile) {
    var t = profile.getTimezone(spec_profile) 
        ? moment(minuteTime).tz(profile.getTimezone(spec_profile)) 
        : moment(minuteTime);
    
    var mmtMidnight = t.clone().startOf('day');
    var timeAsSecondsFromMidnight = t.clone().diff(mmtMidnight, 'seconds');
    
    // Find applicable value
    _.each(valueContainer, function(value) {
        if (timeAsSecondsFromMidnight >= value.timeAsSeconds) {
            returnValue = value.value;
        }
    });
};
```

**Key insight:** Nightscout uses moment-timezone to convert UTC time to profile timezone, then finds seconds from midnight to locate the applicable schedule segment.

---

## 3. Timezone Handling Semantics

### 3.1 Comparison Matrix

| Aspect | Loop | AAPS | Trio | Nightscout |
|--------|------|------|------|------------|
| **Storage Format** | `TimeZone` object | `utcOffset: Long` (ms) | IANA string (from NS) | IANA string |
| **Stored With** | Each schedule | Each event | Profile document | Profile document |
| **DST Awareness** | Yes (Foundation TimeZone) | No (fixed offset at event time) | Yes (via moment-tz) | Yes (via moment-tz) |
| **Travel Handling** | Manual update or auto-detect | Manual profile switch | Downloads new profile | Requires manual edit |

### 3.2 Loop Timezone Handling

```swift
// Each schedule has its own timezone
public var timeZone: TimeZone

// Timezone-aware schedule lookup
func scheduleOffset(for date: Date) -> TimeInterval {
    let interval = date.timeIntervalSinceReferenceDate + 
                   TimeInterval(timeZone.secondsFromGMT(for: date))
    // ...
}
```

**Behavior:**
- Schedule stored with timezone (e.g., `America/New_York`)
- `secondsFromGMT(for: date)` returns correct offset for that date (DST-aware)
- If user travels, schedule shifts automatically if timezone changes
- Can be manually adjusted in settings

### 3.3 AAPS UTC Offset Handling

```kotlin
// ProfileSwitch stores offset at event creation time
override var utcOffset: Long = TimeZone.getDefault().getOffset(timestamp).toLong()
```

**Behavior:**
- Offset captured at moment of profile switch
- Does NOT automatically adjust for DST
- Travel requires new ProfileSwitch with correct offset
- `timeshift` modifier can compensate for timezone changes

**Example - Jet Lag Adjustment:**
```kotlin
ProfileSwitch(
    profileName = "Day Profile (Shifted)",
    timeshift = 3600000,  // +1 hour shift
    percentage = 100,
    duration = 0  // Permanent
)
```

### 3.4 DST Transition Edge Cases

| Scenario | Loop | AAPS | Nightscout |
|----------|------|------|------------|
| **Spring Forward** | Schedule auto-adjusts | No auto-adjust (uses captured offset) | moment-tz handles |
| **Fall Back** | Schedule auto-adjusts | No auto-adjust | moment-tz handles |
| **Duplicate Hour** | Latest entry wins | Offset is fixed | moment-tz resolves |
| **Missing Hour** | Interpolates to next | Offset is fixed | moment-tz resolves |

**GAP-TZ-001**: AAPS's fixed `utcOffset` approach does not handle DST transitions automatically. Users must manually create a new ProfileSwitch or use `timeshift` to compensate.

---

## 4. Profile Switch Semantics

### 4.1 Semantic Comparison

| Concept | Loop | AAPS | Trio/Nightscout |
|---------|------|------|-----------------|
| **Complete Profile Change** | Edit `TherapySettings` directly | `ProfileSwitch` with new `profileName` | `Profile Switch` treatment |
| **Temporary Insulin Adjustment** | `TemporaryScheduleOverride.insulinNeedsScaleFactor` | `ProfileSwitch.percentage != 100` | `Profile Switch` (semantic loss) |
| **Schedule Time Shift** | Not supported natively | `ProfileSwitch.timeshift` | `Profile Switch` (semantic loss) |
| **Temporary Duration** | `Override.duration` | `ProfileSwitch.duration` | `duration` field |
| **Override vs Profile** | Distinct concepts | Same entity (ProfileSwitch) | Distinct treatments |

### 4.2 Loop Override Model

```swift
// Source: LoopKit/LoopKit/TemporaryScheduleOverride.swift
public struct TemporaryScheduleOverride: Hashable {
    public var context: Context          // preMeal, workout, preset, custom
    public var settings: TemporaryScheduleOverrideSettings
    public var startDate: Date
    public var duration: Duration        // finite(TimeInterval) or indefinite
    public var actualEnd: End            // natural, early, deleted
    public let syncIdentifier: UUID
}

public struct TemporaryScheduleOverrideSettings: Hashable {
    public var targetRange: ClosedRange<HKQuantity>?
    public var insulinNeedsScaleFactor: Double?  // 0.5 = 50% insulin
}
```

**Behavior:**
- Overrides are *overlays* on existing settings
- Only specified fields are modified
- Duration tracked with clear end semantics
- Supersession is explicit (new override ends previous)

### 4.3 AAPS ProfileSwitch Semantic Overloading

AAPS's `ProfileSwitch` serves multiple semantic purposes:

| Use Case | `profileName` | `percentage` | `timeshift` | `duration` |
|----------|---------------|--------------|-------------|------------|
| Complete switch | Changes | 100 | 0 | 0 |
| Temp % adjustment | "(+10%)" suffix | 110 | 0 | >0 |
| Jet lag shift | "(Shifted)" suffix | 100 | >0 | 0 |
| Combined | Descriptive name | !=100 | !=0 | varies |

**Nightscout Upload:**
```kotlin
fun ProfileSwitch.toNSProfileSwitch(): NSProfileSwitch = NSProfileSwitch(
    date = timestamp,
    profile = profileName,           // Effective name (may include modifiers)
    originalProfileName = originalProfileName,
    profileJson = toProfileJson(),   // Full profile data
    percentage = percentage,
    timeShift = timeshift,
    duration = duration
)
```

**Problem:** Nightscout stores `percentage` and `timeShift` fields but doesn't semantically distinguish between:
- True profile switch (user changed to different profile)
- Temporary adjustment (user increased insulin by 10%)
- Schedule shift (user compensating for travel)

This is documented as **GAP-002** in the traceability matrix.

### 4.4 Trio Profile Handling

Trio downloads profiles from Nightscout and uses them locally:

```swift
struct FetchedNightscoutProfileStore: JSON {
    let defaultProfile: String
    let store: [String: ScheduledNightscoutProfile]
}
```

**Behavior:**
- Profiles authored in Nightscout or by another app
- Trio downloads and selects `defaultProfile`
- Local overrides use separate `Override` entity (not synced to NS)
- `TempTarget` synced separately as treatment

---

## 5. Sync Direction & Conflict Resolution

### 5.1 Sync Direction Matrix

| System | Profile Upload | Profile Download | Identity Field |
|--------|----------------|------------------|----------------|
| **Loop** | Optional (configurable) | No | N/A |
| **AAPS** | Yes (on ProfileSwitch) | Yes (can import) | `interfaceIDs.nightscoutId` |
| **Trio** | No (local only) | Yes (primary source) | `_id` from NS |
| **xDrip4iOS** | No | Yes (read-only) | N/A |

### 5.2 Loop Profile Sync

```swift
// Profile upload is optional
// Source: Loop/Managers/SettingsManager.swift
// No automatic profile download - settings are device-authoritative
```

**Characteristics:**
- Loop is authoritative for its own settings
- Can optionally upload profile to Nightscout for visualization
- Does not receive profile updates from Nightscout
- No conflict resolution needed (single source of truth)

### 5.3 AAPS Bidirectional Sync

```kotlin
// AAPS tracks sync state via InterfaceIDs
data class InterfaceIDs(
    var nightscoutId: String? = null,
    var pumpId: Long? = null,
    var pumpType: InterfaceIDs.PumpType? = null,
    var pumpSerial: String? = null
)
```

**Characteristics:**
- ProfileSwitch uploaded to Nightscout treatments
- Can import profiles from Nightscout
- `nightscoutId` tracks sync state
- Last-write-wins for conflicts

### 5.4 Trio Download-Only Sync

```swift
// Trio fetches profiles from Nightscout
// Source: Trio/Sources/APS/OpenAPS/OpenAPS.swift
func fetchProfile() async throws -> FetchedNightscoutProfileStore {
    let response = try await nightscoutAPI.fetchProfile()
    return response
}
```

**Characteristics:**
- Nightscout is authoritative for base profiles
- Local overrides don't sync (GAP: override semantics lost)
- TempTargets sync as separate treatments
- No conflict - NS is source of truth

---

## 6. Interoperability Gaps

### 6.1 Format Transformation Gaps

| Gap ID | Description | Impact |
|--------|-------------|--------|
| **GAP-PROFILE-001** | Loop uses HealthKit units (`HKQuantity`), Nightscout uses strings | Unit precision may be lost during conversion |
| **GAP-PROFILE-002** | AAPS blocks are duration-based, Nightscout is start-time based | Requires conversion logic |
| **GAP-PROFILE-003** | Loop has no profile naming | Cannot reference profiles by name in cross-system scenarios |

### 6.2 Semantic Information Gaps

| Gap ID | Description | Impact |
|--------|-------------|--------|
| **GAP-002** | AAPS ProfileSwitch semantic overloading | Nightscout can't distinguish profile change from adjustment |
| **GAP-TZ-001** | AAPS uses fixed utcOffset, others use IANA timezone | DST transitions not automatically handled in AAPS |
| **GAP-OVERRIDE-001** | Loop overrides are distinct, AAPS uses ProfileSwitch | Override intent lost when viewing AAPS data in Loop-centric tools |

### 6.3 Sync Identity Gaps

| Gap ID | Description | Impact |
|--------|-------------|--------|
| **GAP-003** | No unified profile identity across systems | Cannot correlate same profile across different apps |
| **GAP-PROFILE-004** | Loop doesn't download profiles | Loop settings can't be remotely updated via Nightscout |

### 6.4 Recommendations

#### Short-Term Workarounds

1. **Profile Name Encoding**: AAPS already encodes adjustment type in profile name (`"Day (+10%)"`, `"Day (Shifted)"`)
   - Parsers can detect patterns to recover semantic intent
   - Not reliable for complex combinations

2. **Preserve Original Fields**: When uploading, include both:
   - `profile`: Effective profile name
   - `originalProfileName`: Base profile name
   - `percentage`, `timeShift`: Modifier values

3. **Timezone Normalization**: Always include IANA timezone alongside UTC offset
   - Store both `timezone: "America/New_York"` and `utcOffset: -18000000`
   - Allows DST-aware clients to use IANA, offset-only clients to use fixed offset

#### Long-Term Solutions

1. **Distinct Event Types** (Recommended):
   ```json
   {
     "eventType": "Profile Adjustment",  // New type
     "baseProfile": "Day Profile",
     "insulinAdjustment": 1.10,
     "timeShift": 0,
     "targetAdjustment": null,
     "duration": 7200
   }
   ```

2. **Unified Profile Identity**:
   - Add `profileId` field (UUID) that persists across systems
   - Allow cross-referencing profiles by ID rather than name

3. **IANA Timezone Requirement**:
   - Make `timezone` field required in profile collection
   - Deprecate reliance on fixed offset alone

---

## 7. Code References

| Concept | Loop | AAPS | Trio | Nightscout |
|---------|------|------|------|------------|
| Profile Structure | `LoopKit/TherapySettings.swift` | `database/entities/ProfileSwitch.kt` | `Trio/Sources/Models/FetchedProfile.swift` | `lib/profilefunctions.js` |
| Time-Based Schedule | `LoopKit/DailyValueSchedule.swift` | `database/entities/data/Block.kt` | Uses NS format | `lib/profilefunctions.js#L59` |
| Override Model | `LoopKit/TemporaryScheduleOverride.swift` | Via ProfileSwitch | `Trio/Sources/Models/Override.swift` | `lib/plugins/careportal.js` |
| Timezone Handling | `DailyValueSchedule.scheduleOffset()` | `ProfileSwitch.utcOffset` | From NS profile | `moment.tz()` |
| Sync Logic | `NightscoutService/Extensions/` | `plugins/sync/nsclientV3/` | `Sources/APS/Storage/` | API v1/v3 |

---

## 8. Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial unified comparison document |

---

## Cross-References

- [AAPS ProfileSwitch Semantics](../../mapping/aaps/profile-switch.md) - Deep dive on GAP-002
- [Nightscout Data Collections](../../mapping/nightscout/data-collections.md) - Profile collection mapping
- [Cross-Project Terminology Matrix](../../mapping/cross-project/terminology-matrix.md) - Term translations
- [Loop Nightscout Sync](../../mapping/loop/nightscout-sync.md) - Loop upload details
- [xDrip4iOS Profile Handling](../../mapping/xdrip4ios/profile-handling.md) - Download-only implementation
