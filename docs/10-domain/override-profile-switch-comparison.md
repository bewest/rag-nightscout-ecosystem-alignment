# Override and Profile Switch Comparison

> **Sources**: Loop, AAPS, Trio, Nightscout  
> **Last Updated**: 2026-01-28

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

Uses Loop's eventTypes:
- `Temporary Override`
- `Temporary Target`

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

| System | Override Type | NS eventType |
|--------|---------------|--------------|
| Loop | TemporaryScheduleOverride | `Temporary Override` |
| AAPS | ProfileSwitch | `Profile Switch` |
| AAPS | TempTarget | `Temporary Target` |
| Trio | Override | `Temporary Override` |
| Trio | TempTarget | `Temporary Target` |

---

## Gaps Identified

### GAP-OVERRIDE-001: No unified override/profile-switch model

**Description**: Loop uses `Temporary Override`, AAPS uses `Profile Switch`, and they have different semantics. No way to translate between them.

**Impact**:
- Loop overrides appear as different eventType than AAPS profile switches
- Cannot query "what therapy adjustment was active at time T" across systems
- Follower apps must handle multiple eventTypes

**Remediation**: Define abstract `TherapyAdjustment` schema that both map to.

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

## Summary Table

| Aspect | Loop | AAPS | Trio | Recommendation |
|--------|------|------|------|----------------|
| **Primary Model** | Override | ProfileSwitch | Override | Document both |
| **Target Handling** | In override | Separate TT | Both | Accept difference |
| **Insulin Scaling** | Factor (0.0-2.0) | Percentage (1-200) | Percentage | Map: % = factor×100 |
| **End Tracking** | ✅ | ❌ | ❌ | Add to AAPS/Trio |
| **NS eventType** | Temporary Override | Profile Switch | Temporary Override | Accept difference |

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
- `externals/Trio/LoopKit/LoopKit/TemporaryScheduleOverride.swift`

### Nightscout
- `externals/cgm-remote-monitor/lib/plugins/loop.js` (Temporary Override)
- `externals/cgm-remote-monitor/lib/plugins/openaps.js` (Temporary Target)
- `externals/cgm-remote-monitor/lib/plugins/careportal.js` (Profile Switch)
