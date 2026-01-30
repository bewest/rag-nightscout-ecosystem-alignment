# Profile Switch Sync Comparison: AAPS vs Loop vs Trio

> **Date**: 2026-01-30  
> **Status**: Complete  
> **Domain**: Sync & Identity / Profile

---

## Executive Summary

Profile synchronization to Nightscout differs fundamentally between systems. **AAPS uses `Profile Switch` treatment events** that embed complete profile data, while **Loop uploads to the `profile` collection** without treatment events. **Trio fetches profiles from Nightscout but does not upload Profile Switch events**.

| System | Upload Method | Collection | eventType |
|--------|---------------|------------|-----------|
| AAPS | PUT (v3 API) | `treatments` | `Profile Switch` |
| Loop | POST | `profile` | N/A |
| Trio | POST | `profile` | N/A (fetch only) |

---

## 1. AAPS Profile Switch Model

### Entity Definition

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/ProfileSwitch.kt:32-54
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
    var timeshift: Long,  // [milliseconds]
    var percentage: Int,  // 1 ~ XXX [%]
    override var duration: Long, // [milliseconds]
    var insulinConfiguration: InsulinConfiguration
) : TraceableDBEntry, DBEntryWithTimeAndDuration
```

### Key Characteristics

- **Duration=0**: Permanent profile change (new baseline)
- **Duration>0**: Temporary profile activation
- **Percentage**: Allows scaling (100% = normal, 150% = 50% more insulin)
- **Timeshift**: Rotate schedule forward/backward in time

### Nightscout Sync Format

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/treatment/NSProfileSwitch.kt:6-32
data class NSProfileSwitch(
    override var date: Long?,
    override val identifier: String?,
    override val eventType: EventType,  // "Profile Switch"
    val profileJson: JSONObject?,       // Complete embedded profile
    val profile: String,                // Profile name
    val originalProfileName: String?,
    val timeShift: Long?,
    val percentage: Int?,
    val duration: Long?,                // milliseconds
    val originalDuration: Long?
) : NSTreatment
```

### Sync Behavior

1. **Upload**: AAPS uploads ProfileSwitch to `treatments` collection with eventType `Profile Switch`
2. **Embedded JSON**: Complete profile data included in `profileJson` field
3. **Deduplication**: Uses `interfaceIDs.nightscoutId` for identity
4. **Event Bus**: `EventProfileSwitchChanged` triggers sync to pumps and NS

---

## 2. Loop Profile Model

### TherapySettings (Not a "Switch")

Loop does not have a "Profile Switch" concept. Instead, it has **TherapySettings** which are uploaded to the Nightscout `profile` collection.

```swift
// loop:NightscoutService/NightscoutServiceKit/NightscoutService.swift:367
uploader.uploadProfiles(stored.compactMap { $0.profileSet }, completion: completion)
```

### Profile Collection Format

Loop uploads a `ProfileSet` to the `profile` collection:

```swift
// loop:NightscoutService/NightscoutServiceKit/Extensions/ProfileSet.swift:34-96
extension ProfileSet {
    var therapySettings: TherapySettings? {
        // Converts NS profile to Loop TherapySettings
        let basalSchedule = BasalRateSchedule(
            dailyItems: profile.basal.map { 
                RepeatingScheduleValue(startTime: $0.offset, value: $0.value) 
            },
            timeZone: profile.timeZone)
        // ... ISF, CR, targets
    }
}
```

### Key Differences from AAPS

| Aspect | Loop | AAPS |
|--------|------|------|
| Collection | `profile` | `treatments` |
| eventType | N/A | `Profile Switch` |
| Duration concept | N/A | Permanent vs Temporary |
| Percentage scaling | N/A | Supported |
| Timeshift | N/A | Supported |

### Sync Behavior

1. **Upload**: Loop uploads to `profile` collection (not treatments)
2. **No eventType**: Not a treatment event
3. **Fetch**: Can fetch TherapySettings from NS profile
4. **Implicit activation**: Profile is "current" without explicit switch events

---

## 3. Trio Profile Model

### Fetch-Only Pattern

Trio primarily **fetches** profiles from Nightscout rather than uploading them.

```swift
// trio:Trio/Sources/Models/RawFetchedProfile.swift:3-24
struct FetchedNightscoutProfileStore: JSON {
    let _id: String
    let defaultProfile: String
    let startDate: String
    let mills: Decimal
    let enteredBy: String
    let store: [String: ScheduledNightscoutProfile]
}

struct FetchedNightscoutProfile: JSON {
    let dia: Decimal
    let target_low: [NightscoutTimevalue]
    let target_high: [NightscoutTimevalue]
    let sens: [NightscoutTimevalue]
    let basal: [NightscoutTimevalue]
    let carbratio: [NightscoutTimevalue]
}
```

### Upload Behavior

```swift
// trio:Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:411-440
func uploadProfile(_ profile: NightscoutProfileStore) async throws {
    // POST to profile collection
    request.httpMethod = "POST"
    // Uses api-secret header authentication
}
```

### Key Characteristics

- **Import settings**: `importSettings()` fetches NS profile for initial config
- **No Profile Switch events**: Does not upload to treatments collection
- **Local overrides**: Override presets stored locally, not synced as Profile Switches

---

## 4. Nightscout Profile Collection vs Treatment

### Profile Collection (`profile`)

Static storage for profile definitions:

```javascript
// ns:lib/api3/generic/setup.js:65-72
if (_.includes(enabledCols, 'profile')) {
    cols.profile = new Collection({
        colName: 'profile',
        storageColName: env.profile_collection || 'profile',
        fallbackGetDate: fallbackCreatedAt,
        dedupFallbackFields: ['created_at'],
        fallbackDateField: 'created_at'
    });
}
```

### Profile Switch Treatment

Event recording when profile becomes active:

```javascript
// ns:lib/plugins/careportal.js:92-94
{ val: 'Profile Switch'
  , name: 'Profile Switch'
  , bg: true, insulin: false, carbs: false, duration: true, profile: true
}
```

### Relationship

| Concept | Nightscout Location | Purpose |
|---------|---------------------|---------|
| Profile Definition | `profile` collection | Store basal/ISF/CR schedules |
| Profile Activation | `treatments` with eventType | Record when profile became active |

---

## 5. Sync Identity Comparison

| System | Identity Field | Example |
|--------|---------------|---------|
| AAPS | `interfaceIDs.nightscoutId` | `"65a1b2c3..."` |
| Loop | N/A (profile `_id`) | N/A |
| Trio | N/A (profile `_id`) | N/A |

### Deduplication Behavior

- **AAPS**: Uses `identifier` field on treatments for dedup
- **Loop**: Replaces profile collection document
- **Trio**: Replaces profile collection document

---

## 6. Cross-System Scenarios

### Scenario A: AAPS User Checks NS Web

1. AAPS uploads `Profile Switch` treatment
2. NS web shows profile change in timeline
3. Profile name and percentage visible

### Scenario B: Loop User Checks NS Web

1. Loop uploads to `profile` collection
2. NS web shows current profile in settings
3. **No treatment event** in timeline for profile change

### Scenario C: Trio Fetches from NS

1. User configures profile in NS web
2. Trio fetches via `importSettings()`
3. Profile applied locally without treatment event

---

## 7. Gap Analysis

### GAP-SYNC-035: No Profile Switch Events from Loop/Trio

**Description**: Loop and Trio upload profiles to the `profile` collection but do not create `Profile Switch` treatment events. This means profile change history is not tracked in the treatments timeline.

**Affected Systems**: Loop, Trio, Nightscout

**Impact**: 
- Cannot retrospectively analyze when profiles changed
- Different timeline visibility vs AAPS users
- Caregivers cannot see profile change events in NS reports

**Remediation**: Controllers could optionally create `Profile Switch` treatment events when uploading new profiles.

---

### GAP-SYNC-036: ProfileSwitch Embedded JSON Size

**Description**: AAPS embeds complete profile JSON in `profileJson` field of Profile Switch treatments. This duplicates data and increases treatment document size.

**Affected Systems**: AAPS, Nightscout

**Impact**:
- Large treatment documents
- Data duplication between `profile` and `treatments` collections
- Potential sync performance impact

**Remediation**: Consider storing profile reference ID instead of embedded JSON.

---

### GAP-SYNC-037: Percentage/Timeshift Not Portable

**Description**: AAPS Profile Switch supports `percentage` (insulin scaling) and `timeshift` (schedule rotation) features that are not understood by Loop or Trio.

**Affected Systems**: AAPS, Loop, Trio

**Impact**:
- Multi-controller households may see confusing profile data
- Percentage adjustments not reflected in Loop/Trio if fetched

**Remediation**: Document as AAPS-specific feature; Loop/Trio should ignore or warn on percentage!=100.

---

## 8. Source Files Analyzed

| System | File | Purpose |
|--------|------|---------|
| AAPS | `database/entities/ProfileSwitch.kt` | Entity definition |
| AAPS | `core/nssdk/localmodel/treatment/NSProfileSwitch.kt` | NS sync model |
| AAPS | `core/nssdk/mapper/TreatmentMapper.kt:238-263` | Conversion logic |
| Loop | `NightscoutServiceKit/NightscoutService.swift:367` | Profile upload |
| Loop | `NightscoutServiceKit/Extensions/ProfileSet.swift` | NS→TherapySettings |
| Trio | `Models/RawFetchedProfile.swift` | Fetch model |
| Trio | `Services/Network/Nightscout/NightscoutAPI.swift:411` | Upload method |
| NS | `lib/api3/generic/setup.js:65-72` | Profile collection config |
| NS | `lib/plugins/careportal.js:92-94` | Profile Switch eventType |

---

## 9. Terminology Mapping

| Concept | AAPS | Loop | Trio | Nightscout |
|---------|------|------|------|------------|
| Active profile | `EffectiveProfileSwitch` | `TherapySettings` | Local settings | Current profile |
| Profile event | `ProfileSwitch` entity | N/A | N/A | `Profile Switch` treatment |
| Scaling | `percentage` | N/A | N/A | `percentage` field |
| Schedule shift | `timeshift` | N/A | N/A | `timeShift` field |
| Embedded data | `basalBlocks`, `isfBlocks` | N/A | N/A | `profileJson` |

---

## 10. Requirements

### REQ-SYNC-051: Profile Change Visibility

**Statement**: Controllers SHOULD create `Profile Switch` treatment events when the active profile changes.

**Rationale**: Enables retrospective analysis of profile changes in Nightscout timeline.

**Verification**: Check treatments collection for `eventType: "Profile Switch"` after profile change.

**Gap**: GAP-SYNC-035

---

### REQ-SYNC-052: Percentage Handling

**Statement**: Controllers fetching Profile Switch treatments with `percentage != 100` SHOULD apply scaling or warn user.

**Rationale**: AAPS percentage adjustments affect actual insulin delivery.

**Verification**: Test with percentage=150 profile switch; verify scaled or warned.

**Gap**: GAP-SYNC-037

---

### REQ-SYNC-053: Profile Deduplication

**Statement**: Controllers uploading profiles SHOULD use consistent identity to prevent duplicates.

**Rationale**: Avoid multiple profile documents for same logical profile.

**Verification**: Upload same profile twice; verify single document in collection.

**Gap**: GAP-SYNC-036

---

## 11. Nocturne-Specific Findings

See [Nocturne ProfileSwitch Analysis](nocturne-profileswitch-analysis.md) for detailed Nocturne implementation analysis.

**Key Discovery**: Nocturne **actively applies** `percentage` and `timeshift` from ProfileSwitch treatments when computing profile values for algorithm calculations, while cgm-remote-monitor only displays these values.

| Server | Percentage Effect | Timeshift Effect |
|--------|-------------------|------------------|
| **Nocturne** | basal×%, ISF÷%, CR÷% | Schedule rotation |
| **cgm-remote-monitor** | Display only | Display only |

**Gap Added**: GAP-NOCTURNE-004

**Requirements Added**: REQ-SYNC-054, REQ-SYNC-055, REQ-SYNC-056
