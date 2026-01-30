# Override and Temporary Target Sync Comparison

> **Status**: Complete  
> **Last Updated**: 2026-01-30  
> **Task**: Compare how overrides/temp targets sync to Nightscout

## Executive Summary

Loop and AAPS have fundamentally different concepts that both sync to Nightscout:

| Concept | Loop | AAPS | Nightscout eventType |
|---------|------|------|---------------------|
| **Override** | `TemporaryScheduleOverride` | N/A | `Override` (custom) |
| **Temp Target** | (part of override) | `TemporaryTarget` | `Temporary Target` |

Key difference: Loop's override modifies **both** target range AND insulin needs (sensitivity); AAPS temp target modifies **only** target range.

## Loop Override Sync

### Source Files
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/OverrideTreament.swift:1-61`
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/TemporaryScheduleOverride.swift:1-80`

### Override Structure

Loop's `TemporaryScheduleOverride` contains:

```swift
// LoopKit TemporaryScheduleOverride components
struct TemporaryScheduleOverride {
    var startDate: Date
    var duration: Duration         // .finite(TimeInterval) or .indefinite
    var settings: Settings         // targetRange + insulinNeedsScaleFactor
    var context: Context           // .custom, .preMeal, .legacyWorkout, .preset
    var syncIdentifier: UUID       // For deduplication
}
```

### Sync to Nightscout

Loop creates an `OverrideTreatment` for Nightscout:

```swift
// OverrideTreament.swift:14-60
extension OverrideTreatment {
    convenience init(override: TemporaryScheduleOverride) {
        // Convert targetRange to mg/dL for Nightscout
        let nsTargetRange: ClosedRange<Double>?
        if let targetRange = override.settings.targetRange {
            nsTargetRange = ClosedRange(uncheckedBounds: (
                lower: targetRange.lowerBound.doubleValue(for: .milligramsPerDeciliter),
                upper: targetRange.upperBound.doubleValue(for: .milligramsPerDeciliter)))
        }
        
        // Map context to reason string
        let reason: String
        switch override.context {
        case .custom: reason = "Custom Override"
        case .legacyWorkout: reason = "Workout"
        case .preMeal: reason = "Pre-Meal"
        case .preset(let preset): reason = preset.symbol + " " + preset.name
        }
        
        // Track remote origin
        let enteredBy = override.enactTrigger.isRemote ? 
            "Loop (via remote command)" : "Loop"
        
        self.init(
            startDate: override.startDate,
            enteredBy: enteredBy,
            reason: reason,
            duration: duration,
            correctionRange: nsTargetRange,
            insulinNeedsScaleFactor: override.settings.insulinNeedsScaleFactor,
            id: override.syncIdentifier.uuidString
        )
    }
}
```

### Nightscout Treatment Fields

Loop syncs these fields for overrides:

| Field | Source | Example |
|-------|--------|---------|
| `eventType` | Fixed | `"Override"` or `"Temporary Override"` |
| `created_at` | `startDate` | ISO 8601 timestamp |
| `enteredBy` | `"Loop"` or `"Loop (via remote command)"` | |
| `reason` | Context name | `"Pre-Meal"`, `"🏃 Running"` |
| `duration` | `duration.finite` or 0 for indefinite | Minutes |
| `correctionRange` | `[min, max]` | `[80, 90]` |
| `insulinNeedsScaleFactor` | Settings | `0.8` for -20% |
| `_id` / `identifier` | `syncIdentifier.uuidString` | UUID |

## AAPS Temp Target Sync

### Source Files
- `externals/AndroidAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/TemporaryTargetExtension.kt:1-46`
- `externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/treatment/NSTemporaryTarget.kt:1-47`

### Temp Target Structure

AAPS's `TemporaryTarget` (TT) contains:

```kotlin
// Database entity TT
data class TT(
    val timestamp: Long,
    val utcOffset: Long,
    val reason: Reason,           // CUSTOM, HYPOGLYCEMIA, ACTIVITY, EATING_SOON, etc.
    val highTarget: Double,       // Upper bound (mg/dL)
    val lowTarget: Double,        // Lower bound (mg/dL)
    val duration: Long,           // Milliseconds
    val ids: IDs                  // nightscoutId, pumpId, etc.
)
```

### Sync to Nightscout

AAPS converts to `NSTemporaryTarget`:

```kotlin
// TemporaryTargetExtension.kt:27-43
fun TT.toNSTemporaryTarget(): NSTemporaryTarget =
    NSTemporaryTarget(
        eventType = EventType.TEMPORARY_TARGET,
        isValid = isValid,
        date = timestamp,
        utcOffset = T.msecs(utcOffset).mins(),
        reason = reason.toReason(),
        targetTop = highTarget,
        targetBottom = lowTarget,
        units = NsUnits.MG_DL,
        duration = duration,
        identifier = ids.nightscoutId,
        pumpId = ids.pumpId,
        pumpType = ids.pumpType?.name,
        pumpSerial = ids.pumpSerial,
        endId = ids.endId
    )
```

### Nightscout Treatment Fields

AAPS syncs these fields for temp targets:

| Field | Source | Example |
|-------|--------|---------|
| `eventType` | Fixed | `"Temporary Target"` |
| `created_at` | `timestamp` | ISO 8601 timestamp |
| `targetTop` | `highTarget` | `120` (mg/dL) |
| `targetBottom` | `lowTarget` | `120` (mg/dL) |
| `duration` | Duration | Milliseconds |
| `reason` | Reason enum | `"Activity"`, `"Eating Soon"` |
| `identifier` | `nightscoutId` | UUID |

### AAPS Temp Target Reasons

```kotlin
// NSTemporaryTarget.kt:33-40
enum class Reason(val text: String) {
    CUSTOM("Custom"),
    HYPOGLYCEMIA("Hypo"),
    ACTIVITY("Activity"),
    EATING_SOON("Eating Soon"),
    AUTOMATION("Automation"),
    WEAR("Wear")
}
```

## Nightscout Storage

### eventType Handling

```javascript
// cgm-remote-monitor/lib/client/careportal.js:323-325
if (data.eventType.indexOf('Temporary Target Cancel') > -1) {
    data.duration = 0;
    data.eventType = 'Temporary Target';
}
```

### Cancellation Pattern

Both systems use `duration = 0` to cancel:

```javascript
// lib/plugins/treatmentnotify.js:115
if (lastTreatment.duration === 0 && eventType === 'Temporary Target') {
    // This is a cancellation
}
```

## Comparison Matrix

| Feature | Loop Override | AAPS Temp Target |
|---------|--------------|------------------|
| **eventType** | `Override` | `Temporary Target` |
| **Target range** | `correctionRange` [min, max] | `targetTop`, `targetBottom` |
| **Insulin adjustment** | `insulinNeedsScaleFactor` | ❌ Not supported |
| **Reason field** | Free text from context | Enum (6 values) |
| **Preset support** | Yes (symbol + name) | Limited (reason enum) |
| **Duration** | Seconds, 0 = indefinite | Milliseconds |
| **Sync identity** | `syncIdentifier` UUID | `identifier` + pump IDs |
| **Cancel mechanism** | Duration = 0 | Duration = 0 |

## Interoperability Gaps

### GAP-OVRD-001: Different eventTypes

**Description**: Loop uses `Override`, AAPS uses `Temporary Target` - they don't map to each other.

**Evidence**:
- Loop: `OverrideTreament.swift` creates eventType `Override`
- AAPS: `NSTemporaryTarget.kt:29` uses `EventType.TEMPORARY_TARGET`

**Impact**: A Loop override is not recognized as a temp target by AAPS and vice versa.

**Remediation**: Nightscout could map between them, or each app could recognize both types.

### GAP-OVRD-002: insulinNeedsScaleFactor Not in AAPS

**Description**: Loop overrides can adjust insulin sensitivity; AAPS temp targets cannot.

**Evidence**:
- Loop: `OverrideTreament.swift:59` includes `insulinNeedsScaleFactor`
- AAPS: `NSTemporaryTarget.kt` has no equivalent field

**Impact**: Loop overrides with insulin adjustment don't translate to AAPS.

**Remediation**: Document as design difference; AAPS uses profile switching for insulin adjustment.

### GAP-OVRD-003: Reason Enum vs Free Text

**Description**: AAPS uses enum with 6 values; Loop uses free text from preset names.

**Evidence**:
- AAPS: `NSTemporaryTarget.Reason` enum with CUSTOM, HYPOGLYCEMIA, ACTIVITY, etc.
- Loop: `OverrideTreament.swift:30-39` maps context to string

**Impact**: Loop preset names like "🏃 Running" don't map to AAPS reasons.

**Remediation**: Nightscout could normalize reasons; apps could recognize common patterns.

### GAP-OVRD-004: Duration Units Differ

**Description**: Loop uses seconds; AAPS uses milliseconds.

**Evidence**:
- Loop: `TemporaryScheduleOverride.swift:26-31` uses TimeInterval (seconds)
- AAPS: `NSTemporaryTarget.kt:24` documents milliseconds

**Impact**: Duration conversion required when syncing.

**Remediation**: Nightscout normalizes to minutes; apps should convert accordingly.

## Sync Identity Fields

### Loop
```swift
id: override.syncIdentifier.uuidString
```

### AAPS
```kotlin
identifier = ids.nightscoutId,
pumpId = ids.pumpId,
pumpType = ids.pumpType?.name,
pumpSerial = ids.pumpSerial,
endId = ids.endId
```

### Deduplication

| System | Primary Key | Secondary Keys |
|--------|-------------|----------------|
| Loop | `syncIdentifier` (UUID) | None |
| AAPS | `identifier` | `pumpId`, `pumpSerial`, `endId` |

## Requirements

### REQ-OVRD-001: eventType Documentation

**Statement**: Systems MUST document which eventType(s) they use for target overrides.

**Rationale**: Loop `Override` vs AAPS `Temporary Target` causes interoperability confusion.

**Verification**: Documentation review.

### REQ-OVRD-002: Insulin Adjustment Sync

**Statement**: Systems that support insulin sensitivity adjustment SHOULD sync this to Nightscout.

**Rationale**: Loop's `insulinNeedsScaleFactor` is important for understanding override behavior.

**Verification**: Field presence in synced treatments.

### REQ-OVRD-003: Duration Unit Normalization

**Statement**: Systems MUST normalize duration to consistent units when syncing.

**Rationale**: Loop (seconds) vs AAPS (milliseconds) requires conversion.

**Verification**: Duration value validation in synced treatments.

## References

- [Nightscout Treatments Schema](https://nightscout.github.io/nightscout/setup_variables/#treatments)
- [Loop Override Documentation](https://loopkit.github.io/loopdocs/operation/features/overrides/)
- [AAPS Temp Target Documentation](https://androidaps.readthedocs.io/en/latest/Usage/temptarget.html)
