# Loop Override Behavior

This document details Loop's override system as implemented in `TemporaryScheduleOverride.swift` and `TemporaryScheduleOverrideHistory.swift`.

## Overview

Loop's override system provides:
1. **Temporary adjustments** to basal, ISF, CR, and target range
2. **Preset management** for commonly-used overrides
3. **Supersession handling** for overlapping overrides
4. **Remote control support** via Nightscout

---

## Override Data Model

### Source: `TemporaryScheduleOverride.swift`
**File**: `loop:LoopKit/LoopKit/TemporaryScheduleOverride.swift`

```swift
public struct TemporaryScheduleOverride: Hashable {
    public var context: Context
    public var settings: TemporaryScheduleOverrideSettings
    public var startDate: Date
    public let enactTrigger: EnactTrigger
    public let syncIdentifier: UUID
    public var actualEnd: End = .natural
    public var duration: Duration
}
```

### Context Types

```swift
public enum Context: Hashable {
    case preMeal        // Built-in pre-meal override
    case legacyWorkout  // Built-in workout override
    case preset(TemporaryScheduleOverridePreset)  // User-defined preset
    case custom         // One-off custom override
}
```

### Duration Types

```swift
public enum Duration: Hashable, Comparable {
    case finite(TimeInterval)  // Specific duration
    case indefinite            // Until cancelled
}
```

**Key behavior**: Indefinite overrides use `.infinity` for timeInterval but encode as `0` when uploading to Nightscout.

### Enact Trigger

```swift
public enum EnactTrigger: Hashable {
    case local                // User activated on device
    case remote(String)       // Remote command with address
}
```

Tracks whether override was started locally or via remote command.

### End Types

```swift
public enum End: Equatable, Hashable, Codable {
    case natural     // Ended at scheduled time
    case early(Date) // Cancelled before scheduled end
    case deleted     // Override was superseded before starting
}
```

---

## Override Settings

### Source: `TemporaryScheduleOverrideSettings.swift`
**File**: `loop:LoopKit/LoopKit/TemporaryScheduleOverrideSettings.swift`

```swift
public struct TemporaryScheduleOverrideSettings: Hashable, Equatable {
    public var targetRange: ClosedRange<HKQuantity>?
    public var insulinNeedsScaleFactor: Double?
}
```

### Target Range Override

When set, replaces the user's normal target range:
```swift
settings.targetRange = ClosedRange(
    uncheckedBounds: (
        lower: HKQuantity(unit: .milligramsPerDeciliter, doubleValue: 100),
        upper: HKQuantity(unit: .milligramsPerDeciliter, doubleValue: 110)
    )
)
```

### Insulin Needs Scale Factor

Multiplier applied to insulin delivery:
- `0.5` = 50% of normal (exercise mode)
- `1.0` = normal (default)
- `1.5` = 150% of normal (sick day)

**Applied to**:
- Basal rates
- ISF (inverse - higher scale factor means lower sensitivity)
- CR (inverse - higher scale factor means lower carb ratio)

---

## Override History Management

### Source: `TemporaryScheduleOverrideHistory.swift`
**File**: `loop:LoopKit/LoopKit/TemporaryScheduleOverrideHistory.swift`

This class manages the lifecycle of all overrides:

```swift
public final class TemporaryScheduleOverrideHistory {
    private var recentEvents: [OverrideEvent] = []
    public var relevantTimeWindow: TimeInterval = TimeInterval.hours(10)
    private var modificationCounter: Int64
}
```

### Recording an Override

```swift
public func recordOverride(_ override: TemporaryScheduleOverride?, at enableDate: Date = Date()) {
    guard override != lastUndeletedEvent?.override else { return }
    
    if let override = override {
        record(override, at: enableDate)
    } else {
        cancelActiveOverride(at: enableDate)
    }
    delegate?.temporaryScheduleOverrideHistoryDidUpdate(self)
}
```

**Key behavior**:
- Ignores duplicate recordings
- `nil` override means cancel current
- Notifies delegate on any change

---

## Supersession Logic

### Core Supersession Rule

When a new override is recorded, any overlapping overrides are handled:

```swift
private func record(_ override: TemporaryScheduleOverride, at enableDate: Date) {
    // Check for modification of existing entry by syncIdentifier
    // ...
    
    // Delete any overrides starting on or after new override
    deleteEventsStartingOnOrAfter(override.startDate)
    
    // Cancel active override at moment before new one starts
    let overrideEnd = min(override.startDate.nearestPrevious, enableDate)
    cancelActiveOverride(at: overrideEnd)
    
    // Record the new override
    let enabledEvent = OverrideEvent(override: override, modificationCounter: modificationCounter)
    recentEvents.append(enabledEvent)
}
```

### Supersession Cases

**Case 1: New override starts now**
```
Before: Override A: 10:00-11:00 (active)
Action: Start Override B at 10:30

After:
  Override A: 10:00-10:30 (ended early)
  Override B: 10:30-11:30 (active)
```

**Case 2: New override scheduled for future**
```
Before: Override A: 10:00-11:00 (active)
Action: Schedule Override B for 10:45-11:45

After:
  Override A: 10:00-10:45 (will end early when B starts)
  Override B: 10:45-11:45 (scheduled)
```

**Case 3: Cancel active override**
```
Before: Override A: 10:00-11:00 (active)
Action: Cancel at 10:30

After:
  Override A: 10:00-10:30 (ended early)
```

### Delete vs Cancel

```swift
private func deleteEventsStartingOnOrAfter(_ date: Date) {
    recentEvents.mutateEach { (event) in
        if event.override.startDate >= date {
            event.override.actualEnd = .deleted  // Never executed
        }
    }
}

private func cancelActiveOverride(at date: Date) {
    // ... find active override
    if recentEvents[index].override.startDate > date {
        recentEvents[index].override.actualEnd = .deleted
    } else {
        recentEvents[index].override.actualEnd = .early(date)
    }
}
```

- **Deleted** (`.deleted`): Override never actually executed (superseded before start)
- **Ended Early** (`.early(Date)`): Override executed but cancelled before scheduled end

---

## Schedule Application

### Basal Rate Override

```swift
public func resolvingRecentBasalSchedule(_ base: BasalRateSchedule, relativeTo referenceDate: Date = Date()) -> BasalRateSchedule {
    filterRecentEvents(relativeTo: referenceDate)
    return overridesReflectingEnabledDuration(relativeTo: referenceDate).reduce(base) { base, override in
        base.applyingBasalRateMultiplier(from: override, relativeTo: referenceDate)
    }
}
```

Applies `insulinNeedsScaleFactor` to basal rates during override windows.

### ISF Override

```swift
public func resolvingRecentInsulinSensitivitySchedule(_ base: InsulinSensitivitySchedule, relativeTo referenceDate: Date = Date()) -> InsulinSensitivitySchedule {
    // ... similar pattern, applies inverse of scale factor
}
```

**Important**: ISF is divided by `insulinNeedsScaleFactor`:
- Scale factor 0.5 → ISF × 2 (more sensitive, less insulin)
- Scale factor 2.0 → ISF × 0.5 (less sensitive, more insulin)

### Carb Ratio Override

```swift
public func resolvingRecentCarbRatioSchedule(_ base: CarbRatioSchedule, relativeTo referenceDate: Date = Date()) -> CarbRatioSchedule {
    // ... similar pattern, applies inverse of scale factor
}
```

---

## Validation and Safety

### Overlap Prevention

```swift
private func validateOverridesReflectingEnabledDuration(_ overrides: [TemporaryScheduleOverride]) {
    let overlappingOverridePairIndices: [(Int, Int)] =
        Array(overrides.enumerated())
            .allPairs()
            .compactMap {
                if override1.activeInterval.intersects(override2.activeInterval) {
                    return (index1, index2)
                }
                return nil
            }
    
    guard invalidOverrideIndices.isEmpty else {
        // Save tainted history for debugging
        taintedEventLog = recentEvents
        // Remove conflicting overrides
        recentEvents.removeAll(at: invalidOverrideIndices)
        // CRASH - this should never happen
        preconditionFailure("No overrides should overlap.")
    }
}
```

**Critical**: Loop crashes if overlapping overrides are detected. This ensures algorithm never sees conflicting state.

---

## Presets

### Source: `TemporaryScheduleOverridePreset.swift`
**File**: `loop:LoopKit/LoopKit/TemporaryScheduleOverridePreset.swift`

```swift
public struct TemporaryScheduleOverridePreset: Hashable {
    public let id: UUID
    public var symbol: String
    public var name: String
    public var settings: TemporaryScheduleOverrideSettings
    public var duration: TemporaryScheduleOverride.Duration
}
```

Users can define presets with:
- Custom emoji symbol
- Descriptive name
- Pre-configured settings
- Default duration

---

## Remote Control

### Activating Override Remotely

Via Nightscout, remote users can:
1. Start a preset override by name
2. Start a custom override with parameters
3. Cancel the active override

**Source**: `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/Actions/OverrideAction.swift`

```swift
public struct OverrideAction: Codable {
    public let name: String
    public let durationTime: TimeInterval?
    public let remoteAddress: String
}
```

**Source**: `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/Actions/OverrideCancelAction.swift`

```swift
public struct OverrideCancelAction: Codable {
    public let remoteAddress: String
}
```

When activated remotely, `enactTrigger` is set to `.remote(address)` where address identifies the sender.

---

## Nightscout Integration

### Override Upload

**Source**: `loop:NightscoutService/NightscoutServiceKit/Extensions/OverrideTreament.swift`

```swift
extension OverrideTreatment {
    convenience init(override: LoopKit.TemporaryScheduleOverride) {
        // Maps Loop override to Nightscout treatment
        
        let reason: String = switch override.context {
        case .custom: "Custom Override"
        case .legacyWorkout: "Workout"
        case .preMeal: "Pre-Meal"
        case .preset(let preset): preset.symbol + " " + preset.name
        }
        
        let enteredBy = switch override.enactTrigger {
        case .remote: "Loop (via remote command)"
        case .local: "Loop"
        }
        
        self.init(
            startDate: override.startDate,
            enteredBy: enteredBy,
            reason: reason,
            duration: duration,
            correctionRange: nsTargetRange,
            insulinNeedsScaleFactor: override.settings.insulinNeedsScaleFactor,
            remoteAddress: remoteAddress,
            id: override.syncIdentifier.uuidString
        )
    }
}
```

### Field Mapping

| Loop Field | Nightscout Field |
|------------|------------------|
| `startDate` | `timestamp` |
| `context` (name) | `reason` |
| `settings.targetRange` | `correctionRange` |
| `settings.insulinNeedsScaleFactor` | `insulinNeedsScaleFactor` |
| `duration` | `duration` (0 = indefinite) |
| `enactTrigger` | `enteredBy` |
| `syncIdentifier` | `_id` |

### Status Upload

Loop also uploads current override status to `devicestatus.loop.override`:

```swift
var overrideStatus: NightscoutKit.OverrideStatus {
    guard let scheduleOverride = scheduleOverride, scheduleOverride.isActive() else {
        return NightscoutKit.OverrideStatus(timestamp: date, active: false)
    }
    
    return NightscoutKit.OverrideStatus(
        name: scheduleOverride.context.name,
        timestamp: date,
        active: true,
        currentCorrectionRange: currentCorrectionRange,
        duration: remainingDuration,
        multiplier: scheduleOverride.settings.insulinNeedsScaleFactor
    )
}
```

---

## Alignment Gaps

### GAP-001: Supersession Tracking

**Issue**: Nightscout does not track supersession relationships.

**Loop's behavior**: When Override B supersedes Override A:
- Override A has `actualEnd = .early(date)`
- The relationship is implicit (temporal ordering)

**Proposal**: Add `supersedes` field to Nightscout treatments:
```json
{
  "eventType": "Temporary Override",
  "supersedes": "previous-override-id",
  "supersededAt": "2026-01-16T10:30:00Z"
}
```

### Missing Override History

Nightscout receives individual override treatments but loses:
- `actualEnd` type (natural vs early vs deleted)
- Full event history with modification counters
- Validation/tainted event logs

### Duration Encoding

Loop uses `TimeInterval.infinity` for indefinite overrides.
Nightscout uses `0` for indefinite.
**This is correctly mapped** in the upload code.
