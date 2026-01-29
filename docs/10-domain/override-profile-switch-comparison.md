# Override and Profile Switch Comparison

> **Sources**: Loop, AAPS, Trio, Nightscout  
> **Last Updated**: 2026-01-29  
> **Analysis Depth**: Deep (source code analysis)

## Overview

This document compares how Loop, AAPS, and Trio handle temporary therapy adjustments (overrides, profile switches, temp targets) and how these sync to Nightscout.

## Concept Mapping

| Concept | Loop | AAPS | Trio | Nightscout eventType |
|---------|------|------|------|---------------------|
| **Therapy Override** | `TemporaryScheduleOverride` | `ProfileSwitch` | `Override` | `Temporary Override` |
| **Target Range Change** | Part of Override | `TempTarget` | `TempTarget` | `Temporary Target` |
| **Profile Change** | N/A (single profile) | `ProfileSwitch` | N/A | `Profile Switch` |
| **Calculated Profile** | N/A | `EffectiveProfileSwitch` | N/A | N/A |

### Key Semantic Differences

| Aspect | Loop | AAPS | Trio |
|--------|------|------|------|
| **Separate Target** | No (target in override) | Yes (TempTarget entity) | Yes (TempTarget entity) |
| **Percentage Scaling** | `insulinNeedsScaleFactor` | `percentage` field | `percentage` field |
| **Multiple Profiles** | No | Yes (full profiles) | No |
| **Profile Shifting** | No | Yes (`timeshift` field) | No |

---

## Loop: TemporaryScheduleOverride

### Data Model

**Source**: `LoopKit/LoopKit/TemporaryScheduleOverride.swift`

```swift
struct TemporaryScheduleOverride {
    var context: Context           // .preMeal, .legacyWorkout, .preset(), .custom
    var settings: TemporaryScheduleOverrideSettings
    var startDate: Date
    var duration: Duration         // .finite(TimeInterval), .indefinite
    var actualEnd: End             // .natural, .early(Date), .deleted
    let enactTrigger: EnactTrigger // .local, .remote(String)
    let syncIdentifier: UUID
}
```

### Context Types

| Context | Purpose | Duration |
|---------|---------|----------|
| `.preMeal` | Pre-meal temp target | Typically 1 hour |
| `.legacyWorkout` | Exercise mode | User-defined |
| `.preset(...)` | Named preset | From preset |
| `.custom` | Ad-hoc override | User-defined |

### Settings

**Source**: `LoopKit/LoopKit/TemporaryScheduleOverrideSettings.swift`

| Field | Type | Description |
|-------|------|-------------|
| `targetRange` | `DoubleRange?` | Override glucose target |
| `insulinNeedsScaleFactor` | `Double?` | Multiplier for basal/CR/ISF (0.5 = 50% less insulin) |

### End State Tracking

| End Type | Meaning |
|----------|---------|
| `.natural` | Override ended at scheduled time |
| `.early(Date)` | User cancelled before scheduled end |
| `.deleted` | Override was deleted (error state) |

### Nightscout Sync

**eventType**: `Temporary Override`

**Uploaded Fields**:
- `reason` (override name)
- `duration` (minutes)
- `correctionRange` (target range)
- `insulinNeedsScaleFactor`
- `notes`

**GAP**: `actualEnd` state not synced (see GAP-001)

---

## AAPS: ProfileSwitch + EffectiveProfileSwitch

### ProfileSwitch Model

**Source**: `database/impl/src/main/kotlin/app/aaps/database/entities/ProfileSwitch.kt`

```kotlin
data class ProfileSwitch(
    var timestamp: Long,
    var duration: Long,           // milliseconds (0 = permanent)
    var profileName: String,
    var percentage: Int,          // 1-XXX% (100 = normal)
    var timeshift: Long,          // milliseconds
    var basalBlocks: List<Block>,
    var isfBlocks: List<Block>,
    var icBlocks: List<Block>,
    var targetBlocks: List<TargetBlock>,
    var insulinConfiguration: InsulinConfiguration
)
```

### EffectiveProfileSwitch Model

**Source**: `database/impl/src/main/kotlin/app/aaps/database/entities/EffectiveProfileSwitch.kt`

The **calculated** profile in effect after applying percentage and timeshift:

```kotlin
data class EffectiveProfileSwitch(
    // Same profile blocks as ProfileSwitch
    var originalProfileName: String,
    var originalPercentage: Int,
    var originalTimeshift: Long,
    var originalDuration: Long
)
```

### Key Features

| Feature | Description |
|---------|-------------|
| **Percentage** | Scale all insulin values (50% = half insulin) |
| **Timeshift** | Shift profile schedule (e.g., +2 hours for travel) |
| **Duration** | 0 = permanent, >0 = temporary |
| **Multiple Profiles** | Can switch between completely different profiles |

### TempTarget (Separate Entity)

**Source**: `database/impl/src/main/kotlin/app/aaps/database/entities/TempTarget.kt`

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | Long | Start time |
| `duration` | Long | Duration (ms) |
| `reason` | Reason | CUSTOM, EATING_SOON, ACTIVITY, HYPOGLYCEMIA, WEAR |
| `lowTarget` | Double | Low target (mg/dL) |
| `highTarget` | Double | High target (mg/dL) |

### Nightscout Sync

**eventTypes**:
- `Profile Switch` - profile name, percentage, timeshift, duration
- `Temporary Target` - target values, duration, reason

---

## Trio: Override + TempTarget

### Override Model

**Source**: `Trio/Sources/Models/Override.swift`

```swift
struct Override {
    let name: String
    let enabled: Bool
    let date: Date
    let duration: Decimal        // minutes
    let indefinite: Bool
    let percentage: Double       // insulin scaling
    let target: Decimal          // target glucose
    let overrideTarget: Bool     // whether to use override target
    let smbIsOff: Bool           // disable SMB
    let isPreset: Bool
    // Advanced settings
    let isfAndCr: Bool           // apply to ISF and CR
    let isf: Bool                // apply to ISF only
    let cr: Bool                 // apply to CR only
    let smbMinutes: Decimal
    let uamMinutes: Decimal
}
```

### TempTarget Model

**Source**: `Trio/Sources/Models/TempTarget.swift`

```swift
struct TempTarget {
    var id: String
    let name: String?
    var createdAt: Date
    let targetTop: Decimal?
    let targetBottom: Decimal?
    let duration: Decimal        // minutes
    let reason: String?
    let halfBasalTarget: Decimal?  // oref1 half-basal target
}
```

### Key Features

| Feature | Description |
|---------|-------------|
| **Granular ISF/CR** | Can apply percentage to ISF, CR, or both |
| **SMB Control** | Can disable SMB during override |
| **halfBasalTarget** | oref1 feature for reduced insulin at high targets |
| **Indefinite** | Override can run until cancelled |

### Nightscout Sync

**eventType**: `Exercise` (NOT `Temporary Override`)

**Key Finding**: Trio does NOT use Loop's `Temporary Override` eventType. Instead, it repurposes the standard `Exercise` eventType:

```swift
// OverrideStored+helper.swift:34-36
enum EventType: String, JSON {
    case nsExercise = "Exercise"
}

// OverrideStorage.swift:261-269
return NightscoutExercise(
    duration: Int(truncating: duration),
    eventType: OverrideStored.EventType.nsExercise,  // "Exercise"
    createdAt: override.date ?? Date(),
    enteredBy: NightscoutExercise.local,  // "Trio"
    notes: override.name ?? "Custom Override",
    id: UUID(uuidString: override.id ?? UUID().uuidString)
)
```

**Uploaded Fields**:
- `eventType`: "Exercise"
- `duration`: minutes (43200 for indefinite = 30 days)
- `notes`: override name
- `enteredBy`: "Trio"
- `created_at`: start timestamp

**Missing from Upload**:
- `percentage` (insulin scaling)
- `target` (override target)
- `smbIsOff`, `smbMinutes`, `uamMinutes` (algorithm controls)

---

## Cross-System Comparison

### Feature Matrix

| Feature | Loop | AAPS | Trio |
|---------|------|------|------|
| **Target Override** | ✅ In override | ✅ TempTarget | ✅ Both |
| **Insulin Scaling** | ✅ Single factor | ✅ Percentage | ✅ Granular |
| **Profile Timeshift** | ❌ | ✅ | ❌ |
| **Multiple Profiles** | ❌ | ✅ | ❌ |
| **SMB Control** | ❌ | ✅ (via settings) | ✅ Explicit |
| **End State Tracking** | ✅ `.actualEnd` | ❌ | ❌ |
| **Indefinite Duration** | ✅ | ❌ (duration=0 is permanent) | ✅ |
| **Presets** | ✅ | ✅ (profiles) | ✅ |

### Duration Semantics

| System | Duration=0 | Indefinite |
|--------|------------|------------|
| **Loop** | N/A (use `.indefinite`) | `.indefinite` enum |
| **AAPS** | Permanent switch | N/A |
| **Trio** | Instant/cancel | `indefinite: true` |
| **Nightscout** | Cancel (TT) | Not standard |

### Nightscout eventType Mapping

| System | Override Type | NS eventType | Notes |
|--------|---------------|--------------|-------|
| Loop | TemporaryScheduleOverride | `Temporary Override` | Custom type, rich data |
| AAPS | ProfileSwitch | `Profile Switch` | Standard NS type, full profile |
| AAPS | TempTarget | `Temporary Target` | Standard NS type |
| **Trio** | Override | `Exercise` | **Repurposed standard type** |
| Trio | TempTarget | `Temporary Target` | Standard NS type |

**Critical Finding**: Trio uses `Exercise` eventType for overrides, NOT `Temporary Override`. This means:
- Trio overrides show as "Exercise" events in Nightscout
- Loop and Trio override data is NOT interchangeable
- Nightscout visualization differs between systems

---

## Gaps Identified

### GAP-OVERRIDE-001: Incompatible eventTypes Across Systems

**Description**: Each system uses a different Nightscout eventType:
- Loop: `Temporary Override` (custom type)
- AAPS: `Profile Switch` (standard type)
- Trio: `Exercise` (repurposed standard type)

**Impact**:
- Overrides from one system don't appear correctly in another system's views
- No unified "what adjustment was active at time T" query
- Careportal doesn't have unified override entry
- Follower apps must handle three different patterns

**Remediation**: Define standard `Override` eventType in Nightscout with fields from all systems.

### GAP-OVERRIDE-002: AAPS percentage vs Loop insulinNeedsScaleFactor

**Description**: 
- Loop: `insulinNeedsScaleFactor = 0.5` means 50% less insulin need
- AAPS: `percentage = 50` means 50% of normal insulin

These are mathematically equivalent but semantically inverted.

**Impact**: Follower apps must invert the value when displaying.

**Remediation**: Document the mapping: `aaps.percentage = loop.insulinNeedsScaleFactor * 100`

### GAP-OVERRIDE-003: TempTarget vs Override separation inconsistent

**Description**:
- Loop: Target is part of override (`targetRange` in settings)
- AAPS/Trio: TempTarget is a separate entity from ProfileSwitch/Override

**Impact**:
- Combining target + insulin adjustment requires different logic per system
- May have active TempTarget AND ProfileSwitch simultaneously in AAPS

**Remediation**: Accept as fundamental design difference; document in terminology matrix.

### GAP-OVERRIDE-004: Trio advanced override settings not in Nightscout

**Description**: Trio's `smbIsOff`, `isfAndCr`, `smbMinutes`, `uamMinutes` fields have no Nightscout representation.

**Impact**: Following a Trio user, cannot see full override configuration.

**Remediation**: Add extension fields to Nightscout treatment schema.

---

## Sync Identity Patterns

| System | ID Field | Type | Storage | Deduplication |
|--------|----------|------|---------|---------------|
| Loop | `syncIdentifier` | UUID | Memory + NS | Client-side |
| AAPS | `interfaceIDs.nightscoutId` | String | Room DB | Server-side (v3) |
| Trio | `id` | UUID string | CoreData | Client-side |

### Loop Sync Identity

```swift
// TemporaryScheduleOverride.swift:56-57
public let syncIdentifier: UUID

// OverrideTreament.swift:59
self.init(..., id: override.syncIdentifier.uuidString)
```

### AAPS Sync Identity

```kotlin
// ProfileSwitch.kt:39-40
@Embedded
override var interfaceIDs_backing: InterfaceIDs? = InterfaceIDs()

// ProfileSwitchExtension.kt:61
identifier = ids.nightscoutId
```

### Trio Sync Identity

```swift
// OverrideStored+CoreDataProperties.swift:15
@NSManaged var id: String?

// OverrideStorage.swift:127-128
newOverride.id = UUID().uuidString
```

---

## Summary Table

| Aspect | Loop | AAPS | Trio | Recommendation |
|--------|------|------|------|----------------|
| **Primary Model** | Override | ProfileSwitch | Override | Document both |
| **Target Handling** | In override | Separate TT | Both | Accept difference |
| **Insulin Scaling** | Factor (0.0-2.0) | Percentage (1-200) | Percentage | Map: % = factor×100 |
| **End Tracking** | ✅ | ❌ | ❌ | Add to AAPS/Trio |
| **NS eventType** | Temporary Override | Profile Switch | **Exercise** | Standardize to Override |
| **Sync Identity** | syncIdentifier (UUID) | interfaceIDs | id (UUID string) | All use UUID pattern |

---

## Source Files Reference

### Loop
- `externals/LoopWorkspace/LoopKit/LoopKit/TemporaryScheduleOverride.swift`
- `externals/LoopWorkspace/LoopKit/LoopKit/TemporaryScheduleOverrideSettings.swift`
- `externals/LoopWorkspace/LoopKit/LoopKit/TemporaryScheduleOverrideHistory.swift`

### AAPS
- `externals/AndroidAPS/database/impl/src/main/kotlin/app/aaps/database/entities/ProfileSwitch.kt`
- `externals/AndroidAPS/database/impl/src/main/kotlin/app/aaps/database/entities/EffectiveProfileSwitch.kt`
- `externals/AndroidAPS/database/impl/src/main/kotlin/app/aaps/database/entities/TempTarget.kt`

### Trio
- `externals/Trio/Trio/Sources/Models/Override.swift`
- `externals/Trio/Trio/Sources/Models/TempTarget.swift`
- `externals/Trio/Model/Classes+Properties/OverrideStored+CoreDataProperties.swift`
- `externals/Trio/Model/Helper/OverrideStored+helper.swift` (EventType = Exercise)
- `externals/Trio/Trio/Sources/APS/Storage/OverrideStorage.swift` (Nightscout upload)
- `externals/Trio/Trio/Sources/Models/NightscoutExercise.swift`

### Nightscout
- `externals/cgm-remote-monitor-official/lib/server/loop.js:62-73` (Temporary Override handling)
- `externals/cgm-remote-monitor-official/lib/plugins/loop.js`
- `externals/cgm-remote-monitor-official/lib/plugins/openaps.js` (Temporary Target)
- `externals/cgm-remote-monitor-official/lib/plugins/careportal.js` (Profile Switch)
