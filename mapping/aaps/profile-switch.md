# AAPS ProfileSwitch Semantics

This document describes AAPS's ProfileSwitch entity and its semantic differences from Nightscout's Profile Switch treatment, addressing GAP-002.

## Overview

AAPS's `ProfileSwitch` is a powerful but semantically overloaded entity that can represent:

1. **Complete profile change** - Switching to a different profile
2. **Percentage adjustment** - Temporarily adjusting all insulin delivery
3. **Time shift** - Shifting the profile schedule
4. **Combination** - Any combination of the above

Nightscout treats all of these as "Profile Switch" events without distinguishing the semantic intent.

## Database Entity

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/ProfileSwitch.kt
data class ProfileSwitch(
    override var id: Long = 0,
    override var timestamp: Long,
    override var utcOffset: Long,
    
    // Full profile data
    var basalBlocks: List<Block>,     // Basal rate schedule
    var isfBlocks: List<Block>,       // ISF schedule
    var icBlocks: List<Block>,        // IC (carb ratio) schedule
    var targetBlocks: List<TargetBlock>,  // Target glucose schedule
    var glucoseUnit: GlucoseUnit,
    
    // Profile identification
    var profileName: String,
    
    // Modifiers
    var timeshift: Long,              // Time shift in milliseconds
    var percentage: Int,              // Insulin percentage (100 = normal)
    override var duration: Long,      // Duration in milliseconds (0 = permanent)
    
    // Insulin configuration at time of switch
    var insulinConfiguration: InsulinConfiguration
)
```

## Semantic Scenarios

### Scenario 1: Complete Profile Change

User switches from "Day Profile" to "Night Profile":

```kotlin
ProfileSwitch(
    profileName = "Night Profile",
    percentage = 100,
    timeshift = 0,
    duration = 0,  // Permanent
    basalBlocks = nightProfileBasals,
    // ... other profile settings
)
```

**Nightscout Event**: Profile Switch to "Night Profile" ✓

### Scenario 2: Temporary Insulin Adjustment

User increases insulin delivery by 10% for exercise recovery:

```kotlin
ProfileSwitch(
    profileName = "Day Profile (+10%)",
    percentage = 110,
    timeshift = 0,
    duration = 7200000,  // 2 hours
    basalBlocks = dayProfileBasals,  // Same as current profile
    // ... same profile settings, pre-adjusted by percentage
)
```

**Nightscout Event**: Profile Switch to "Day Profile (+10%)"

**Problem**: Nightscout sees this as a profile change, not an adjustment. The semantic meaning "temporarily increase insulin" is lost.

### Scenario 3: Time Shift

User shifts profile schedule by 1 hour (jet lag adjustment):

```kotlin
ProfileSwitch(
    profileName = "Day Profile (Shifted)",
    percentage = 100,
    timeshift = 3600000,  // 1 hour in ms
    duration = 0,
    basalBlocks = dayProfileBasals,  // Same, but interpreted with shift
)
```

**Nightscout Event**: Profile Switch to "Day Profile (Shifted)"

**Problem**: The time shift concept doesn't translate to Nightscout. A viewer sees a profile switch, not a schedule shift.

### Scenario 4: Combined Adjustment

User both increases insulin and shifts schedule:

```kotlin
ProfileSwitch(
    profileName = "Travel Profile",
    percentage = 120,
    timeshift = -7200000,  // -2 hours
    duration = 86400000,   // 24 hours
)
```

**Nightscout Event**: Profile Switch to "Travel Profile"

**Problem**: Both adjustments are encoded in the profile name or lost entirely.

## Nightscout Model

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/treatment/NSProfileSwitch.kt
data class NSProfileSwitch(
    // ... NSTreatment fields ...
    val profileJson: JSONObject?,     // Full profile data
    val profile: String,              // Profile name (effective)
    val originalProfileName: String?, // Original name before modification
    val timeShift: Long?,             // Time shift in ms
    val percentage: Int?,             // Percentage (100 = normal)
    val duration: Long?,              // Duration in ms (0 = permanent)
    val originalDuration: Long?
)
```

### Key Fields for Semantic Preservation

| Field | Purpose |
|-------|---------|
| `profile` | Effective profile name (may include modifiers) |
| `originalProfileName` | Original unmodified profile name |
| `percentage` | Insulin percentage adjustment |
| `timeShift` | Schedule time shift |
| `duration` | Temporary vs permanent |

## Effective Profile Switch

AAPS also has `EffectiveProfileSwitch` which represents the computed active profile:

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/EffectiveProfileSwitch.kt
data class EffectiveProfileSwitch(
    override var timestamp: Long,
    var basalBlocks: List<Block>,
    var isfBlocks: List<Block>,
    var icBlocks: List<Block>,
    var targetBlocks: List<TargetBlock>,
    var glucoseUnit: GlucoseUnit,
    var originalProfileName: String,
    var originalCustomizedName: String,
    var originalTimeshift: Long,
    var originalPercentage: Int,
    var originalDuration: Long,
    var originalEnd: Long,
    var insulinConfiguration: InsulinConfiguration
)
```

This stores the pre-computed profile values after applying percentage and timeshift.

## Comparison: AAPS vs Loop Overrides

| Concept | AAPS | Loop |
|---------|------|------|
| Override Active | `ProfileSwitch.percentage != 100` | `override != nil` |
| Insulin Adjustment | `percentage` field | `insulinNeedsScaleFactor` |
| Target Adjustment | Pre-baked in profile | `settings.targetRange` |
| Duration | `duration` field | `duration` |
| Supersession | Last switch wins | Explicit cancel/replace |

## Gap Analysis (GAP-002)

### Problem

When AAPS uploads a ProfileSwitch with `percentage=110`:

1. Nightscout stores it as "Profile Switch" event
2. Other clients see a profile change, not an adjustment
3. The `percentage` field is stored but not semantically interpreted
4. Visualization shows profile name, not adjustment context

### Impact

1. **Dashboard confusion**: Users see multiple "profile switches" for adjustments
2. **Analytics distortion**: Reports can't distinguish real switches from adjustments
3. **Interoperability**: Other AID systems can't correctly interpret the intent
4. **Audit trail**: Historical review shows profile changes, not temporary adjustments

### Partial Mitigation

AAPS encodes intent in profile name:
- "Day Profile (+10%)" - percentage adjustment
- "Day Profile (Shifted)" - time shift
- "Travel Profile" - combined

This is a naming convention, not a semantic solution.

## Recommended Improvements

### Option 1: Distinct Event Types

Define separate Nightscout event types:
- `Profile Switch` - Complete profile change
- `Profile Adjustment` - Percentage or target modification
- `Profile Shift` - Time shift only

### Option 2: Semantic Fields

Add standard fields to Profile Switch:
```json
{
  "eventType": "Profile Switch",
  "profile": "Day Profile",
  "insulinAdjustment": 1.10,  // 110%
  "timeShift": 0,
  "targetAdjustment": null,
  "isAdjustment": true,
  "originalProfile": "Day Profile"
}
```

### Option 3: Override Event Type

Adopt Loop's `Temporary Override` pattern for adjustments:
```json
{
  "eventType": "Temporary Override",
  "reason": "Exercise Recovery",
  "insulinNeedsScaleFactor": 1.10,
  "targetTop": 120,
  "targetBottom": 100,
  "duration": 7200
}
```

## Current Workarounds

### For AAPS Users

1. Use descriptive profile names
2. Document adjustments in notes field
3. Track original profile separately

### For Nightscout Report Consumers

1. Check `percentage` field if present
2. Look for patterns in profile names
3. Compare consecutive switches to detect adjustments

### For Cross-System Analysis

1. Parse profile name for hints
2. Check if basalBlocks are proportionally adjusted
3. Use `originalProfileName` if available

## Nightscout Upload Example

```kotlin
// AAPS converts ProfileSwitch to NSProfileSwitch
fun ProfileSwitch.toNSProfileSwitch(): NSProfileSwitch = NSProfileSwitch(
    date = timestamp,
    identifier = interfaceIDs.nightscoutId,
    eventType = EventType.PROFILE_SWITCH,
    profile = profileName,
    originalProfileName = originalProfileName,
    profileJson = toProfileJson(),
    percentage = percentage,
    timeShift = timeshift,
    duration = duration,
    originalDuration = originalDuration
)
```

## Summary

AAPS's ProfileSwitch is semantically richer than Nightscout's Profile Switch:

| AAPS Capability | Nightscout Representation |
|-----------------|---------------------------|
| Complete switch | Profile Switch ✓ |
| Percentage adjustment | Profile Switch (semantic loss) |
| Time shift | Profile Switch (semantic loss) |
| Duration control | Duration field ✓ |
| Original profile tracking | originalProfileName field ✓ |

The key gap is that Nightscout treats all ProfileSwitches uniformly, while AAPS distinguishes between true profile changes and temporary adjustments. This is documented as **GAP-002** in the traceability matrix.
